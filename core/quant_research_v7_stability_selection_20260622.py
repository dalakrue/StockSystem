"""Chronological blocked stability selection for existing causal feature columns."""
from __future__ import annotations

from collections import Counter
from typing import Any
import time

import numpy as np
import pandas as pd

from core.quant_research_v7_contract_20260622 import common_method, deterministic_seed, extract_numeric_features

METHOD_ID = "stability_selection"
MIN_SAMPLE = 80


def chronological_blocked_half_samples(n: int, *, repeats: int = 16) -> list[np.ndarray]:
    """Return contiguous/adjacent chronological half-samples; never shuffle rows."""
    if n < 2:
        return []
    width = max(2, n // 2)
    starts = np.linspace(0, max(0, n - width), num=max(2, repeats), dtype=int)
    return [np.arange(int(start), int(start) + width, dtype=int) for start in starts]


def _fit_selector(x: pd.DataFrame, y_return: pd.Series, y_direction: pd.Series) -> set[str]:
    if x.empty:
        return set()
    clean = x.replace([np.inf, -np.inf], np.nan)
    clean = clean.fillna(clean.median(numeric_only=True)).fillna(0.0)
    scale = clean.std(ddof=0).replace(0.0, 1.0)
    z = (clean - clean.mean()) / scale
    selected: set[str] = set()
    try:
        from sklearn.linear_model import LogisticRegression
        if y_direction.nunique() > 1:
            model = LogisticRegression(l1_ratio=1.0, solver="liblinear", C=0.18, max_iter=300, random_state=0)
            model.fit(z, y_direction)
            coef = np.abs(np.asarray(model.coef_)).max(axis=0)
            selected.update(str(c) for c, value in zip(z.columns, coef) if value > 1e-10)
    except Exception:
        pass
    try:
        from sklearn.linear_model import ElasticNet
        if y_return.std(ddof=0) > 1e-12:
            model = ElasticNet(alpha=0.001, l1_ratio=0.85, max_iter=1000, random_state=0)
            model.fit(z, y_return)
            selected.update(str(c) for c, value in zip(z.columns, np.abs(model.coef_)) if value > 1e-10)
    except Exception:
        pass
    if not selected:
        corr = z.apply(lambda col: abs(col.corr(y_return))).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        selected.update(corr.nlargest(min(5, len(corr))).index.astype(str).tolist())
    return selected


def _session_masks(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    time = pd.to_datetime(frame["event_time_utc"], errors="coerce", utc=True)
    hour = time.dt.hour.fillna(-1).to_numpy()
    return {
        "london": (hour >= 7) & (hour < 16),
        "new_york": (hour >= 12) & (hour < 21),
        "overlap": (hour >= 12) & (hour < 16),
    }


def run_stability_selection(frame: pd.DataFrame, *, generation_id: Any, cutoff_time: Any, canonical: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    x, features = extract_numeric_features(frame)
    n = len(frame)
    if n < MIN_SAMPLE or len(features) < 2:
        return common_method(METHOD_ID, status="INSUFFICIENT_EVIDENCE", sample_count=n, minimum_sample_required=MIN_SAMPLE, cutoff_time=cutoff_time, output_metrics={"feature_count": len(features)}, assumptions=["chronological ordering is meaningful"], limitations=["requires at least two non-constant existing feature columns"])
    close_col = next((c for c in frame.columns if str(c).lower() == "close"), None)
    close = pd.to_numeric(frame[close_col], errors="coerce") if close_col else pd.Series(np.nan, index=frame.index)
    # Build the next-completed-candle return explicitly so the source contains
    # no negative-shift operation and the final incomplete target remains NaN.
    close_values = close.to_numpy(dtype=float, copy=False)
    target_values = np.full(len(close_values), np.nan, dtype=float)
    if len(close_values) > 1:
        previous_close = close_values[:-1]
        next_close = close_values[1:]
        valid_denominator = np.isfinite(previous_close) & np.isfinite(next_close) & (np.abs(previous_close) > 1e-15)
        target_values[:-1][valid_denominator] = (next_close[valid_denominator] / previous_close[valid_denominator]) - 1.0
    target_return = pd.Series(target_values, index=close.index, dtype=float)
    valid = target_return.notna() & np.isfinite(target_return)
    x = x.loc[valid].reset_index(drop=True); y_return = target_return.loc[valid].reset_index(drop=True); y_direction = (y_return > 0).astype(int)
    working = frame.loc[valid].reset_index(drop=True)
    blocks = chronological_blocked_half_samples(len(x), repeats=18)
    counts: Counter[str] = Counter(); selected_sets: list[set[str]] = []
    for idx in blocks:
        chosen = _fit_selector(x.iloc[idx], y_return.iloc[idx], y_direction.iloc[idx])
        selected_sets.append(chosen); counts.update(chosen)
    probabilities = {feature: counts[feature] / max(1, len(blocks)) for feature in features}
    half = max(20, len(x) // 3)
    recent = _fit_selector(x.iloc[-half:], y_return.iloc[-half:], y_direction.iloc[-half:])
    previous = _fit_selector(x.iloc[-2*half:-half] if len(x) >= 2*half else x.iloc[:half], y_return.iloc[-2*half:-half] if len(x) >= 2*half else y_return.iloc[:half], y_direction.iloc[-2*half:-half] if len(x) >= 2*half else y_direction.iloc[:half])
    masks = _session_masks(working)
    session_probs = {}
    for label, mask in masks.items():
        idx = np.flatnonzero(mask)
        chosen = _fit_selector(x.iloc[idx], y_return.iloc[idx], y_direction.iloc[idx]) if len(idx) >= 30 else set()
        session_probs[label] = {feature: float(feature in chosen) for feature in features}
    regime_probs = {feature: None for feature in features}
    regime = str(((canonical or {}).get("regime") or {}).get("major_regime") or "UNAVAILABLE")
    jaccards = []
    for first, second in zip(selected_sets, selected_sets[1:]):
        union = first | second
        jaccards.append(len(first & second) / len(union) if union else 1.0)
    adjacent = float(np.mean(jaccards)) if jaccards else 0.0
    stable = sorted([f for f, p in probabilities.items() if p >= 0.70], key=lambda f: (-probabilities[f], f))
    conditional = sorted([f for f, p in probabilities.items() if 0.45 <= p < 0.70], key=lambda f: (-probabilities[f], f))
    corr = x.corr().abs().fillna(0.0)
    clusters = []
    seen: set[str] = set()
    for feature in features:
        if feature in seen:
            continue
        members = [other for other in features if corr.loc[feature, other] >= 0.85]
        seen.update(members)
        clusters.append({"representative": feature, "members": members, "cluster_stability": float(max(probabilities.get(m, 0.0) for m in members))})
    if stable and adjacent >= 0.55:
        status = "STABLE"
    elif stable or conditional:
        status = "CONDITIONALLY_STABLE"
    else:
        status = "UNSTABLE"
    top = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))[:12]
    output = {
        "overall_selection_probability": {k: round(v, 4) for k, v in top},
        "recent_window_selection_probability": {f: float(f in recent) for f, _ in top},
        "previous_window_selection_probability": {f: float(f in previous) for f, _ in top},
        "regime_selection_probability": {f: regime_probs[f] for f, _ in top},
        "regime_context": regime,
        "london_selection_probability": {f: session_probs["london"][f] for f, _ in top},
        "new_york_selection_probability": {f: session_probs["new_york"][f] for f, _ in top},
        "overlap_selection_probability": {f: session_probs["overlap"][f] for f, _ in top},
        "adjacent_window_stability": round(adjacent, 4),
        "jaccard_stability": round(adjacent, 4),
        "correlated_feature_cluster_stability": clusters[:10],
        "stable_feature_count": len(stable),
        "conditionally_stable_feature_count": len(conditional),
        "top_stable_features": stable[:12],
        "blocked_half_sample_count": len(blocks),
        "seed_hash": deterministic_seed(generation_id, METHOD_ID)[1],
        "runtime_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }
    return common_method(METHOD_ID, status=status, sample_count=len(x), minimum_sample_required=MIN_SAMPLE, cutoff_time=cutoff_time, output_metrics=output, assumptions=["features are already available at each completed H1 event", "local feature relationships are sufficiently stable"], limitations=["shadow selection does not remove production features", "regime-specific probability is unavailable when persisted per-row regime labels are absent"])


__all__ = ["chronological_blocked_half_samples", "run_stability_selection"]
