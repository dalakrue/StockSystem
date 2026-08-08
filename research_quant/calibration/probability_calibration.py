from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import numpy as np

from research_quant.calibration.calibration_metrics import brier_score, log_loss, expected_calibration_error

@dataclass
class FittedCalibrator:
    method: str
    model: Any
    sample_size: int

    def predict(self, raw_probability):
        x = np.clip(np.asarray(raw_probability, dtype=float), 1e-9, 1 - 1e-9)
        if self.method == "identity":
            return x
        if self.method == "platt":
            logits = np.log(x / (1 - x)).reshape(-1, 1)
            return self.model.predict_proba(logits)[:, 1]
        if self.method == "isotonic":
            return np.clip(self.model.predict(x), 0, 1)
        if self.method == "beta":
            features = np.column_stack([np.log(x), np.log(1 - x)])
            return self.model.predict_proba(features)[:, 1]
        raise ValueError(f"unknown calibration method {self.method}")


def fit_calibrator(raw_probability, y_true, method: str) -> FittedCalibrator:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    x = np.clip(np.asarray(raw_probability, dtype=float), 1e-9, 1 - 1e-9)
    y = np.asarray(y_true, dtype=int)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 20 or len(np.unique(y)) < 2:
        return FittedCalibrator("identity", None, len(x))
    if method == "platt":
        model = LogisticRegression(max_iter=1000).fit(np.log(x / (1 - x)).reshape(-1, 1), y)
    elif method == "isotonic":
        model = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    elif method == "beta":
        model = LogisticRegression(max_iter=1000).fit(np.column_stack([np.log(x), np.log(1 - x)]), y)
    elif method == "identity":
        model = None
    else:
        raise ValueError(f"unsupported calibrator {method}")
    return FittedCalibrator(method, model, len(x))


def select_calibrator(calibration_probability, calibration_y, test_probability, test_y, methods=("identity", "platt", "isotonic", "beta")):
    """Select only on an untouched test set using proper scores, never accuracy."""
    candidates = []
    for method in methods:
        try:
            fitted = fit_calibrator(calibration_probability, calibration_y, method)
            predicted = fitted.predict(test_probability)
            metrics = {
                "method": fitted.method, "brier_score": brier_score(test_y, predicted),
                "log_loss": log_loss(test_y, predicted), "ece": expected_calibration_error(test_y, predicted),
                "sample_size": fitted.sample_size,
            }
            metrics["selection_score"] = metrics["brier_score"] + 0.25 * metrics["log_loss"] + metrics["ece"]
            candidates.append((metrics["selection_score"], fitted, metrics))
        except Exception:
            continue
    if not candidates:
        fitted = FittedCalibrator("identity", None, 0)
        return fitted, {"method": "identity", "status": "CALIBRATION_FAILED"}
    _, fitted, metrics = min(candidates, key=lambda item: item[0])
    return fitted, metrics
