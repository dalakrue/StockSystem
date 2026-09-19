"""Filardo-style time-varying transition probability shadow adaptation."""
from __future__ import annotations

from typing import Any, Mapping
import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import clip_probability, common_result, unavailable
from core.hamilton_regime_research_v4_20260622 import _feature_frame

METHOD_ID = "FILARDO_TIME_VARYING_TRANSITION_SHADOW"
PAPER_TITLE = "Business-Cycle Phases and Their Transitional Dynamics"
PAPER_AUTHORS = "Andrew J. Filardo"


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -35.0, 35.0)))


def _ridge_irls(x: np.ndarray, y: np.ndarray, ridge: float = 1.0, iterations: int = 25) -> np.ndarray:
    beta = np.zeros(x.shape[1], dtype=float)
    eye = np.eye(x.shape[1]); eye[0, 0] = 0.0
    for _ in range(iterations):
        p = np.clip(_sigmoid(x @ beta), 1e-5, 1.0 - 1e-5)
        w = np.clip(p * (1.0 - p), 1e-5, None)
        z = x @ beta + (y - p) / w
        xtw = x.T * w
        lhs = xtw @ x + ridge * eye
        rhs = xtw @ z
        new = np.linalg.solve(lhs + 1e-8 * np.eye(lhs.shape[0]), rhs)
        new = np.clip(new, -8.0, 8.0)
        if np.max(np.abs(new - beta)) < 1e-6:
            beta = new
            break
        beta = new
    return beta


def _regime_age(states: np.ndarray) -> np.ndarray:
    age = np.ones(len(states), dtype=float)
    for i in range(1, len(states)):
        age[i] = age[i - 1] + 1.0 if states[i] == states[i - 1] else 1.0
    return age


def run_filardo_transition_model(
    frame: pd.DataFrame,
    identity: Mapping[str, Any],
    hamilton: Mapping[str, Any],
    *,
    settled_outcomes: pd.DataFrame | None = None,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    n = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
    minimum = 240
    try:
        if str(hamilton.get("status")) != "AVAILABLE":
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="RIDGE_IRLS_CAUSAL_ADAPTATION", sample_count=0, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["Hamilton state probabilities are required before transition estimation."])
        states = np.asarray(hamilton.get("internal_state_sequence") or [], dtype=int)
        indices = np.asarray(hamilton.get("internal_feature_index") or [], dtype=int)
        if len(states) < minimum or len(indices) != len(states):
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="RIDGE_IRLS_CAUSAL_ADAPTATION", sample_count=len(states), minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["Too few aligned Hamilton states."])
        features = _feature_frame(frame, settled_outcomes).loc[indices].copy()
        ret = np.log(frame["close"].astype(float)).diff().loc[indices]
        age = _regime_age(states)
        yz = features["yang_zhang_volatility"].to_numpy(float)
        yz_series = pd.Series(yz)
        yz_baseline = yz_series.rolling(48, min_periods=12).median()
        # Use only observations available at each timestamp for the warm-up period.
        yz_baseline = yz_baseline.fillna(yz_series.expanding(min_periods=1).median()).ffill().fillna(1e-12)
        yz_ratio = yz / np.clip(yz_baseline.to_numpy(float), 1e-12, None)
        compression = pd.to_numeric(frame.get("compression_score", pd.Series(index=frame.index, dtype=float)), errors="coerce").loc[indices]
        if compression.notna().sum() == 0:
            compression = 1.0 / (1.0 + pd.Series(yz_ratio, index=indices))
        abs_ret = pd.Series(np.abs(ret.to_numpy(float)))
        jump_baseline = abs_ret.rolling(48, min_periods=12).median()
        jump_baseline = jump_baseline.fillna(abs_ret.expanding(min_periods=1).median()).ffill().fillna(1e-12)
        jump = abs_ret.to_numpy(float) / np.clip(jump_baseline.to_numpy(float), 1e-12, None)
        roughness = pd.Series(np.abs(np.diff(np.log(np.clip(yz, 1e-12, None)), prepend=np.log(max(yz[0], 1e-12)))), index=indices)
        disagreement = pd.to_numeric(frame.get("forecast_disagreement", pd.Series(index=frame.index, dtype=float)), errors="coerce").loc[indices].fillna(0.0)
        event = pd.to_numeric(frame.get("event_intensity", pd.Series(index=frame.index, dtype=float)), errors="coerce").loc[indices].fillna(0.0)
        quality = pd.to_numeric(frame.get("data_quality_score", pd.Series(index=frame.index, dtype=float)), errors="coerce").loc[indices].fillna(100.0) / 100.0
        interval_miss_rate = np.zeros(len(indices), dtype=float)
        if isinstance(settled_outcomes, pd.DataFrame) and not settled_outcomes.empty:
            hit_col = next((c for c in ("interval_hit", "coverage_flag", "inside_interval") if c in settled_outcomes.columns), None)
            if hit_col:
                misses = 1.0 - pd.to_numeric(settled_outcomes[hit_col], errors="coerce").fillna(1.0).clip(0, 1)
                rolling = misses.rolling(48, min_periods=5).mean().to_numpy(float)
                interval_miss_rate[:] = float(np.nanmean(rolling)) if np.isfinite(rolling).any() else 0.0
        prior_transition = np.r_[0.05, (states[1:] != states[:-1]).astype(float)]
        z = pd.DataFrame({
            "regime_age": np.log1p(age),
            "yz_volatility_ratio": yz_ratio,
            "compression_score": compression.to_numpy(float),
            "jump_proxy": jump,
            "roughness_score": roughness.to_numpy(float),
            "forecast_disagreement": disagreement.to_numpy(float),
            "interval_miss_rate": interval_miss_rate,
            "event_intensity": event.to_numpy(float),
            "data_quality_score": quality.to_numpy(float),
            "previous_transition_probability": prior_transition,
        }).replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
        y = (states[1:] != states[:-1]).astype(float)
        transition_events = int(y.sum())
        if transition_events < 12 or len(y) - transition_events < 30:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="RIDGE_IRLS_CAUSAL_ADAPTATION", sample_count=len(y), effective_sample_count=transition_events,
                minimum_required_samples=minimum, status="INSUFFICIENT_EVIDENCE",
                limitations=[f"Only {transition_events} observed state changes; at least 12 are required."])
        # Freeze features before chronological evaluation.
        feature_names = list(z.columns)
        x_raw = z.iloc[:-1].to_numpy(float)  # all variables are t-1 for transition t
        split = max(180, int(len(y) * 0.70))
        train_x = x_raw[:split]
        mean = train_x.mean(axis=0); std = train_x.std(axis=0); std[std < 1e-8] = 1.0
        x = np.clip((x_raw - mean) / std, -8.0, 8.0)
        design = np.c_[np.ones(len(x)), x]
        beta = _ridge_irls(design[:split], y[:split], ridge=1.5)
        test_p = np.clip(_sigmoid(design[split:] @ beta), 1e-5, 1.0 - 1e-5) if split < len(y) else np.array([])
        brier = float(np.mean((test_p - y[split:]) ** 2)) if len(test_p) else None
        baseline = float(np.mean((np.mean(y[:split]) - y[split:]) ** 2)) if len(test_p) else None
        latest_z = np.clip((z.iloc[-1].to_numpy(float) - mean) / std, -8.0, 8.0)
        p1 = clip_probability(_sigmoid(np.r_[1.0, latest_z] @ beta), floor=1e-5)
        factors = beta[1:] * latest_z
        order = np.argsort(np.abs(factors))[::-1][:5]
        main = [{"factor": feature_names[i], "contribution": float(factors[i])} for i in order]
        stability = 1.0 - min(1.0, float(np.std(test_p)) * 2.0) if len(test_p) else 0.0
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="RIDGE_REGULARIZED_LOGISTIC_TIME_VARYING_TRANSITION_ADAPTATION",
            sample_count=len(y), effective_sample_count=transition_events, minimum_required_samples=minimum,
            status="AVAILABLE", score=(1.0 - brier) if brier is not None else None,
            confidence=max(0.0, 1.0 - (brier or 1.0)), reliability="STABLE" if stability >= 0.50 else "CAUTION",
            train_start=frame.loc[indices[0], "time"], train_end=frame.loc[indices[split], "time"],
            test_start=frame.loc[indices[split + 1], "time"] if split + 1 < len(indices) else None,
            test_end=frame.loc[indices[-1], "time"],
            assumptions=["Transition at t is modeled only from lagged information available at t-1.", "The pseudo-state path is the Hamilton shadow state, not the protected production regime."],
            limitations=["Logistic multi-hour probabilities use a bounded constant-hazard aggregation.", "Few transition events can make coefficient interpretation unstable."],
            continuation_probability_1h=float(1.0 - p1),
            transition_probability_1h=float(p1),
            transition_probability_3h=float(1.0 - (1.0 - p1) ** 3),
            transition_probability_6h=float(1.0 - (1.0 - p1) ** 6),
            expected_remaining_duration_hours=float(min(240.0, 1.0 / max(p1, 1e-5))),
            transition_hazard=float(p1),
            main_transition_factors=main,
            stability_score=float(stability),
            transition_event_count=transition_events,
            frozen_feature_set=feature_names,
            chronological_test_brier=brier,
            chronological_baseline_brier=baseline,
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["Transition evidence fails safely and cannot change the protected regime or direction."])


__all__ = ["run_filardo_transition_model", "_ridge_irls"]
