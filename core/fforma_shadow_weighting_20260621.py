"""Small offline FFORMA-inspired meta-weighting for existing forecast paths.

The online function only loads/evaluates a compact artifact.  Training is an
explicit offline research action and never happens on a normal Streamlit rerun.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
import json
import numpy as np
import pandas as pd

from core.research_validation_common_20260621 import bounded_softmax, finite, json_safe, stable_hash, utc_now_iso

VERSION = "fforma-shadow-weighting-20260621-v1"
DEFAULT_ARTIFACT = Path(__file__).resolve().parents[1] / "data" / "fforma_shadow_artifact_20260621.json"
FEATURES = (
    "adx", "atr_percentile", "di_separation", "regime_age", "compression",
    "session_code", "event_score", "recent_path_mae", "recent_path_crps",
    "coverage_error", "residual_skew", "forecast_disagreement", "shift_score",
)


def train_offline_fforma_artifact(
    training_cases: pd.DataFrame,
    *,
    feature_columns: Sequence[str] = FEATURES,
    model_loss_columns: Mapping[str, str],
    output_path: Path | str = DEFAULT_ARTIFACT,
    ridge: float = 1.0,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fit bounded linear loss models from purged walk-forward cases.

    The caller is responsible for constructing chronological 25-day/regime/
    session/volatility/horizon blocks and proving the purge/embargo policy.
    """
    if not isinstance(training_cases, pd.DataFrame) or training_cases.empty:
        raise ValueError("training_cases must be a non-empty DataFrame")
    features = [c for c in feature_columns if c in training_cases.columns]
    if not features:
        raise ValueError("No configured FFORMA features are available")
    x = training_cases[features].apply(pd.to_numeric, errors="coerce")
    medians = x.median().fillna(0.0)
    x = x.fillna(medians)
    means = x.mean()
    scales = x.std(ddof=0).replace(0, 1.0).fillna(1.0)
    design = np.column_stack([np.ones(len(x)), ((x - means) / scales).to_numpy(float)])
    penalty = np.eye(design.shape[1]); penalty[0, 0] = 0.0
    coefficients: dict[str, list[float]] = {}
    sample_counts: dict[str, int] = {}
    for model, loss_column in model_loss_columns.items():
        if loss_column not in training_cases:
            continue
        y = pd.to_numeric(training_cases[loss_column], errors="coerce")
        valid = y.notna()
        if int(valid.sum()) < max(20, design.shape[1] + 2):
            continue
        d = design[valid.to_numpy()]
        target = y.loc[valid].to_numpy(float)
        beta = np.linalg.solve(d.T @ d + float(ridge) * penalty, d.T @ target)
        coefficients[str(model)] = beta.tolist()
        sample_counts[str(model)] = int(valid.sum())
    if len(coefficients) < 2:
        raise ValueError("At least two existing forecast paths need sufficient offline cases")
    artifact = {
        "version": VERSION,
        "artifact_id": "FFORMA-" + stable_hash([features, coefficients, sample_counts, metadata])[:24],
        "trained_at": utc_now_iso(),
        "mode": "SHADOW",
        "feature_columns": features,
        "feature_medians": medians.to_dict(),
        "feature_means": means.to_dict(),
        "feature_scales": scales.to_dict(),
        "loss_model_coefficients": coefficients,
        "sample_counts": sample_counts,
        "metadata": dict(metadata or {}),
        "purged_walk_forward_required": True,
        "spa_approval_required": True,
        "resource_budget_approval_required": True,
        "production_promotion_allowed": False,
    }
    path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(artifact), ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def load_artifact(path: Path | str = DEFAULT_ARTIFACT) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) and payload.get("version") == VERSION else {}
    except Exception:
        return {}


def shadow_weights(
    current_features: Mapping[str, Any],
    *,
    artifact: Mapping[str, Any] | None = None,
    artifact_path: Path | str = DEFAULT_ARTIFACT,
    minimum_weight: float = 0.05,
    maximum_weight: float = 0.80,
) -> dict[str, Any]:
    payload = dict(artifact or load_artifact(artifact_path))
    if not payload:
        return {"version": VERSION, "status": "NO_OFFLINE_ARTIFACT", "mode": "SHADOW", "weights": {}, "promotion_allowed": False}
    columns = list(payload.get("feature_columns") or [])
    means = payload.get("feature_means") or {}
    scales = payload.get("feature_scales") or {}
    medians = payload.get("feature_medians") or {}
    values = []
    missing = []
    for column in columns:
        value = finite(current_features.get(column), finite(medians.get(column), 0.0))
        if current_features.get(column) in (None, ""):
            missing.append(column)
        values.append((float(value or 0.0) - float(means.get(column, 0.0))) / max(abs(float(scales.get(column, 1.0))), 1e-9))
    design = np.asarray([1.0] + values, dtype=float)
    expected_losses: dict[str, float] = {}
    for model, beta in (payload.get("loss_model_coefficients") or {}).items():
        coefficients = np.asarray(beta, dtype=float)
        if len(coefficients) == len(design):
            expected_losses[str(model)] = float(np.dot(coefficients, design))
    models = list(expected_losses)
    if len(models) < 2:
        return {"version": VERSION, "status": "INVALID_OFFLINE_ARTIFACT", "mode": "SHADOW", "weights": {}, "promotion_allowed": False}
    weights = bounded_softmax([-expected_losses[m] for m in models], minimum=minimum_weight, maximum=maximum_weight)
    result = {
        "version": VERSION,
        "status": "SHADOW_WEIGHTS_AVAILABLE",
        "mode": "SHADOW",
        "artifact_id": payload.get("artifact_id"),
        "weights": {model: round(float(weight), 10) for model, weight in zip(models, weights)},
        "expected_losses": expected_losses,
        "missing_features": missing,
        "promotion_allowed": False,
        "requirements": ["purged_walk_forward", "SPA", "resource_budget", "rollback"],
    }
    result["evaluation_id"] = "FFORMA-EVAL-" + stable_hash(result)[:20]
    return result


__all__ = ["VERSION", "DEFAULT_ARTIFACT", "train_offline_fforma_artifact", "load_artifact", "shadow_weights"]
