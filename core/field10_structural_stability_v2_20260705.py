"""Leakage-safe structural-break and regime protection for Field 10 v3."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import finite

VERSION = "field10-structural-stability-v2-20260705-v1"


def _robust_distance(left: pd.Series, right: pd.Series) -> float:
    a = pd.to_numeric(left, errors="coerce").dropna().to_numpy(float)
    b = pd.to_numeric(right, errors="coerce").dropna().to_numpy(float)
    if len(a) < 12 or len(b) < 12:
        return 0.0
    pooled = np.concatenate([a, b])
    median = float(np.median(pooled))
    mad = float(np.median(np.abs(pooled - median))) * 1.4826
    scale = max(mad, float(np.std(pooled)), 1e-12)
    mean_shift = abs(float(np.mean(a) - np.mean(b))) / scale
    volatility_shift = abs(float(np.std(a) - np.std(b))) / scale
    # Bounded proxy for a distributional distance; transparent and stable on 600 rows.
    return float(np.clip(1.0 - math.exp(-(mean_shift + 0.5 * volatility_shift)), 0.0, 1.0))


def bai_perron_style_breaks(series: pd.Series, *, min_segment: int = 48, max_breaks: int = 3) -> list[dict[str, Any]]:
    """Greedy multiple-break research evidence inspired by Bai-Perron segmentation.

    It is deliberately labelled "style" rather than claiming the exact asymptotic
    test.  Every candidate split is chronological and uses only completed rows.
    """
    values = pd.to_numeric(series, errors="coerce").dropna().reset_index(drop=True)
    if len(values) < 2 * min_segment:
        return []
    segments: list[tuple[int, int]] = [(0, len(values))]
    breaks: list[dict[str, Any]] = []
    for round_number in range(1, int(max_breaks) + 1):
        best: dict[str, Any] | None = None
        for segment_index, (start, end) in enumerate(segments):
            if end - start < 2 * min_segment:
                continue
            for split in range(start + min_segment, end - min_segment + 1):
                distance = _robust_distance(values.iloc[start:split], values.iloc[split:end])
                balance = min(split - start, end - split) / max(end - start, 1)
                score = distance * (0.5 + balance)
                if best is None or score > best["objective"]:
                    best = {"segment_index": segment_index, "start": start, "end": end, "split": split,
                            "distance": distance, "objective": score, "round": round_number}
        if best is None or best["distance"] < 0.20:
            break
        start, end, split = best["start"], best["end"], best["split"]
        segments.pop(best["segment_index"])
        segments.extend([(start, split), (split, end)])
        segments.sort()
        breaks.append(best)
    return sorted(breaks, key=lambda item: item["split"])


def _feature_series(frame: pd.DataFrame, model_errors: pd.Series | None = None, calibration_residuals: pd.Series | None = None) -> dict[str, pd.Series]:
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    returns = np.log(close / close.shift(1))
    realized_volatility = returns.rolling(24, min_periods=12).std(ddof=0)
    momentum = close.pct_change(12)
    future_one = close.pct_change().shift(-1)
    output: dict[str, pd.Series] = {
        "returns": returns,
        "realized_volatility": realized_volatility,
        "momentum_return_relationship": (momentum * future_one).shift(1),
    }
    for name, aliases in {
        "spread": ("spread", "spread_points", "bid_ask_spread"),
        "tick_volume": ("tick_volume", "volume", "tickvol"),
        "session_effects": ("session_code", "session", "broker_hour"),
    }.items():
        for alias in aliases:
            if alias in frame:
                if name == "session_effects":
                    encoded = pd.Series(pd.factorize(frame[alias].astype(str))[0], index=frame.index, dtype=float)
                    output[name] = encoded
                else:
                    output[name] = pd.to_numeric(frame[alias], errors="coerce")
                break
    if model_errors is not None:
        output["model_forecast_errors"] = pd.to_numeric(model_errors, errors="coerce")
    if calibration_residuals is not None:
        output["calibration_residuals"] = pd.to_numeric(calibration_residuals, errors="coerce")
    return output


def _regime_evidence(returns: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if len(values) < 120:
        return {"current_regime_probability": None, "second_regime_probability": None,
                "regime_entropy": None, "regime_persistence": None}
    features = pd.DataFrame({
        "trend": values.rolling(24, min_periods=12).mean(),
        "vol": values.rolling(24, min_periods=12).std(ddof=0),
    }).dropna()
    try:
        from sklearn.cluster import KMeans
        model = KMeans(n_clusters=2, random_state=0, n_init=20).fit(features)
        distances = model.transform(features.tail(1))[0]
        probabilities = np.exp(-distances / max(float(np.std(distances)), 1e-9))
        probabilities = probabilities / probabilities.sum()
        order = np.argsort(probabilities)[::-1]
        labels = model.labels_
        persistence = float(np.mean(labels[1:] == labels[:-1])) if len(labels) > 1 else None
        entropy = float(-np.sum(probabilities * np.log(np.clip(probabilities, 1e-12, 1.0))) / math.log(2.0))
        return {"current_regime_probability": float(probabilities[order[0]]),
                "second_regime_probability": float(probabilities[order[1]]),
                "regime_entropy": entropy, "regime_persistence": persistence,
                "current_regime_label": int(order[0])}
    except Exception:
        return {"current_regime_probability": None, "second_regime_probability": None,
                "regime_entropy": None, "regime_persistence": None}


def structural_stability_evidence(
    frame: pd.DataFrame, *, model_errors: pd.Series | None = None,
    calibration_residuals: pd.Series | None = None,
    adaptive_regime: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if frame is None or len(frame) < 120:
        return {"status": "INSUFFICIENT_EVIDENCE", "structural_entry_permission": "BLOCK"}
    times = pd.to_datetime(frame.get("time", frame.index), errors="coerce", utc=True)
    feature_results: dict[str, Any] = {}
    all_breaks: list[dict[str, Any]] = []
    for name, series in _feature_series(frame, model_errors, calibration_residuals).items():
        breaks = bai_perron_style_breaks(series)
        records = []
        for item in breaks:
            split = int(item["split"])
            record = {**item, "feature": name,
                      "break_time": None if split >= len(times) or pd.isna(times.iloc[split]) else pd.Timestamp(times.iloc[split]).isoformat(),
                      "post_break_h1_count": int(len(series) - split)}
            records.append(record)
            all_breaks.append(record)
        feature_results[name] = records
    latest = max(all_breaks, key=lambda item: item["split"]) if all_breaks else None
    strongest = max(all_breaks, key=lambda item: item["distance"]) if all_breaks else None
    break_strength = 0.0 if strongest is None else float(strongest["distance"])
    post_count = len(frame) if latest is None else int(latest["post_break_h1_count"])
    permission = "BLOCK" if break_strength >= 0.75 and post_count < 96 else "CAUTION" if break_strength >= 0.55 and post_count < 144 else "PASS"
    returns = np.log(pd.to_numeric(frame.get("close"), errors="coerce") / pd.to_numeric(frame.get("close"), errors="coerce").shift(1))
    regime = _regime_evidence(returns)
    return {
        "status": "AVAILABLE", "method": "BAI_PERRON_STYLE_GREEDY_MULTIPLE_BREAK",
        "last_structural_break_time": None if latest is None else latest.get("break_time"),
        "break_strength": break_strength, "post_break_h1_count": post_count,
        "pre_post_distribution_distance": break_strength,
        "structural_entry_permission": permission,
        "actionable_rank_permission": "BLOCK" if permission == "BLOCK" else permission,
        "diagnostic_rank_visible": True,
        "feature_breaks": feature_results, "break_count": len(all_breaks),
        "adaptive_regime_evidence": dict(adaptive_regime or {}), **regime,
        "locked_daily_bias_mutated": False,
    }


__all__ = ["VERSION", "bai_perron_style_breaks", "structural_stability_evidence"]
