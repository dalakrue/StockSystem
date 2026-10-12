"""Causal, selective evaluation patch for Power BI direction accuracy.

The protected point-forecast path is not changed. This module only relabels the
already-produced walk-forward validation rows so direction is evaluated from the
forecast origin, not from the target candle's opening price. Forecasts whose
predicted movement is smaller than a causal volatility threshold are marked
WAIT/NOT_ACTIONABLE and excluded from directional hit-rate claims.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping

import numpy as np
import pandas as pd

VERSION = "powerbi-causal-direction-evaluation-20260621-v1"
MIN_ACTIONABLE_SUPPORT = 20


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _direction(values: pd.Series, *, neutral: pd.Series | None = None) -> pd.Series:
    out = pd.Series("WAIT", index=values.index, dtype="object")
    out.loc[values > 0] = "UP"
    out.loc[values < 0] = "DOWN"
    if neutral is not None:
        out.loc[neutral.fillna(True)] = "WAIT"
    return out


def relabel_direction_accuracy(
    history: pd.DataFrame,
    summary: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return a causally relabelled validation table and compact summary.

    The adaptive threshold at row *t* is based only on realized target ranges
    strictly before *t*. No target direction or future range is used to decide
    whether the prediction at *t* is actionable.
    """
    base_summary = dict(summary or {})
    if not isinstance(history, pd.DataFrame) or history.empty:
        base_summary.update({
            "direction_accuracy_method": VERSION,
            "direction_evidence_status": "INSUFFICIENT_EVIDENCE",
            "actionable_forecasts": 0,
            "actionable_coverage_pct": 0.0,
        })
        return pd.DataFrame() if not isinstance(history, pd.DataFrame) else history.copy(), base_summary

    required = {"time", "Actual High", "Actual Low", "Actual Close", "Pred Open", "Pred Close"}
    if not required.issubset(history.columns):
        base_summary.update({
            "direction_accuracy_method": VERSION,
            "direction_evidence_status": "MISSING_REQUIRED_COLUMNS",
            "legacy_direction_accuracy_pct": base_summary.get("direction_accuracy_pct"),
        })
        return history.copy(), base_summary

    original_order_desc = False
    work = history.copy()
    work["time"] = pd.to_datetime(work["time"], errors="coerce", utc=True)
    work = work.dropna(subset=["time"])
    if len(work) > 1:
        original_order_desc = bool(work["time"].iloc[0] > work["time"].iloc[-1])
    work = work.sort_values("time", kind="mergesort").reset_index(drop=True)

    actual_high = _numeric(work, "Actual High")
    actual_low = _numeric(work, "Actual Low")
    actual_close = _numeric(work, "Actual Close")
    origin = _numeric(work, "Pred Open")
    pred_close = _numeric(work, "Pred Close")

    # Strictly causal threshold: previous target ranges only. The bounded fixed
    # fallback is 0.2 pip for early rows and is not estimated from future data.
    realized_range = (actual_high - actual_low).abs()
    prior_range = realized_range.shift(1).rolling(48, min_periods=12).median()
    early_prior = realized_range.shift(1).expanding(min_periods=1).median()
    prior_range = prior_range.fillna(early_prior).fillna(0.00020)
    threshold = (prior_range * 0.10).clip(lower=0.00002, upper=0.00015)

    pred_move = pred_close - origin
    actual_move = actual_close - origin
    valid = origin.notna() & pred_close.notna() & actual_close.notna() & threshold.notna()
    actionable = valid & (pred_move.abs() >= threshold)
    pred_direction = _direction(pred_move, neutral=~actionable)
    actual_direction = _direction(actual_move, neutral=~valid)
    correct = actionable & (pred_direction == actual_direction) & actual_direction.isin(["UP", "DOWN"])

    work["Forecast Origin"] = origin.round(6)
    work["Predicted Move From Origin"] = pred_move.round(6)
    work["Actual Move From Origin"] = actual_move.round(6)
    work["Causal Direction Threshold"] = threshold.round(6)
    work["Actionable Forecast"] = actionable.astype(bool)
    work["Validated Pred Direction"] = pred_direction
    work["Validated Actual Direction"] = actual_direction
    work["Validated Direction Correct"] = correct.where(actionable, pd.NA).astype("boolean")

    actionable_n = int(actionable.sum())
    valid_n = int(valid.sum())
    accuracy = float(correct.sum() / actionable_n * 100.0) if actionable_n else float("nan")
    coverage = float(actionable_n / valid_n * 100.0) if valid_n else 0.0

    recalls: list[float] = []
    for label in ("UP", "DOWN"):
        mask = actionable & (actual_direction == label)
        if int(mask.sum()) > 0:
            recalls.append(float((pred_direction.loc[mask] == label).mean()))
    balanced = float(np.mean(recalls) * 100.0) if recalls else float("nan")

    legacy = base_summary.get("direction_accuracy_pct")
    status = "PASS" if actionable_n >= MIN_ACTIONABLE_SUPPORT else "INSUFFICIENT_EVIDENCE"
    base_summary.update({
        "legacy_direction_accuracy_pct": legacy,
        "direction_accuracy_pct": round(accuracy, 2) if np.isfinite(accuracy) else None,
        "causal_actionable_direction_accuracy_pct": round(accuracy, 2) if np.isfinite(accuracy) else None,
        "balanced_direction_accuracy_pct": round(balanced, 2) if np.isfinite(balanced) else None,
        "actionable_forecasts": actionable_n,
        "valid_forecasts": valid_n,
        "actionable_coverage_pct": round(coverage, 2),
        "direction_evidence_status": status,
        "direction_accuracy_method": VERSION,
        "minimum_actionable_support": MIN_ACTIONABLE_SUPPORT,
        "direction_accuracy_note": (
            "Direction is measured from forecast origin. Tiny forecast moves are WAIT/NOT_ACTIONABLE; "
            "protected point forecasts are unchanged."
        ),
    })

    if original_order_desc:
        work = work.sort_values("time", ascending=False, kind="mergesort").reset_index(drop=True)
    return work, base_summary


def install(namespace: MutableMapping[str, Any]) -> None:
    """Wrap the existing validation function without replacing forecast logic."""
    name = "_dv_prediction_vs_actual_history_v20260609"
    original = namespace.get(name)
    if not callable(original):
        return
    if getattr(original, "_causal_direction_patch_20260621", False):
        return

    def wrapped(data: Any, lookback: int = 180, horizon: int = 1):
        history, summary = original(data, lookback=lookback, horizon=horizon)
        return relabel_direction_accuracy(history, summary)

    wrapped.__name__ = getattr(original, "__name__", name)
    wrapped.__doc__ = (getattr(original, "__doc__", "") or "") + "\n\nCausal selective direction evaluation applied."
    wrapped._causal_direction_patch_20260621 = True  # type: ignore[attr-defined]
    wrapped._protected_forecast_function = original  # type: ignore[attr-defined]
    namespace[name] = wrapped


__all__ = ["VERSION", "MIN_ACTIONABLE_SUPPORT", "relabel_direction_accuracy", "install"]
