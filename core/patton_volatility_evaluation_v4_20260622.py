"""Patton robust volatility-forecast evaluation on identical settled H1 origins."""
from __future__ import annotations

from typing import Any, Mapping
import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable
from core.realized_garch_research_v4_20260622 import qlike_loss

METHOD_ID = "PATTON_ROBUST_VOLATILITY_EVALUATION"
PAPER_TITLE = "Volatility Forecast Comparison Using Imperfect Volatility Proxies"
PAPER_AUTHORS = "Andrew J. Patton"
VAR_FLOOR = 1e-12


def evaluate_volatility_records(records: pd.DataFrame) -> dict[str, Any]:
    required = {"actual_variance", "realized_garch", "ewma", "rolling_yang_zhang"}
    if not required.issubset(records.columns):
        raise ValueError("Identical evaluation rows for all registered models are unavailable.")
    data = records.replace([np.inf, -np.inf], np.nan).dropna(subset=list(required)).copy()
    if len(data) < 60:
        raise ValueError("At least 60 identical settled forecast origins are required.")
    actual = data["actual_variance"].clip(lower=VAR_FLOOR).to_numpy(float)
    models = [c for c in data.columns if c not in {"actual_variance", "row_index", "return", "time", "regime", "session", "jump_flag"}]
    qlike_by_model: dict[str, float] = {}
    mse_by_model: dict[str, float] = {}
    mae_vol_by_model: dict[str, float] = {}
    medae_by_model: dict[str, float] = {}
    losses: dict[str, np.ndarray] = {}
    for model in models:
        forecast = data[model].clip(lower=VAR_FLOOR).to_numpy(float)
        loss = qlike_loss(actual, forecast)
        losses[model] = loss
        qlike_by_model[model] = float(np.mean(loss))
        mse_by_model[model] = float(np.mean((forecast - actual) ** 2))
        mae_vol_by_model[model] = float(np.mean(np.abs(np.sqrt(forecast) - np.sqrt(actual))))
        medae_by_model[model] = float(np.median(np.abs(forecast - actual)))
    ranking = sorted(qlike_by_model, key=qlike_by_model.get)
    baseline = "rolling_yang_zhang" if "rolling_yang_zhang" in qlike_by_model else ranking[-1]
    skill = {m: float(1.0 - qlike_by_model[m] / qlike_by_model[baseline]) if abs(qlike_by_model[baseline]) > 1e-12 else None for m in ranking}
    paired = {}
    for model in ranking:
        diff = losses[model] - losses[baseline]
        paired[model] = {
            "mean_loss_difference_vs_baseline": float(np.mean(diff)),
            "median_loss_difference_vs_baseline": float(np.median(diff)),
            "support_count": int(len(diff)),
        }
    return {
        "data": data,
        "models": models,
        "candidate_ranking": ranking,
        "qlike_by_model": qlike_by_model,
        "variance_mse_by_model": mse_by_model,
        "volatility_mae_by_model": mae_vol_by_model,
        "median_absolute_error_by_model": medae_by_model,
        "qlike_skill_vs_baseline": skill,
        "paired_loss_differences": paired,
        "baseline": baseline,
        "losses": losses,
    }


def _conditional_summary(data: pd.DataFrame, losses: Mapping[str, np.ndarray]) -> dict[str, Any]:
    conditions: dict[str, np.ndarray] = {}
    if "return" in data.columns:
        absret = np.abs(pd.to_numeric(data["return"], errors="coerce").fillna(0.0).to_numpy(float))
        threshold = float(np.quantile(absret, 0.90))
        conditions["JUMP"] = absret >= threshold
        conditions["NON_JUMP"] = absret < threshold
    if "row_index" in data.columns:
        # Row index is causal completed-H1 position; session cannot be inferred without timestamps.
        pass
    output = {}
    for name, mask in conditions.items():
        if int(mask.sum()) < 20:
            continue
        output[name] = {model: float(np.mean(np.asarray(values)[mask])) for model, values in losses.items()}
    return output


def run_patton_evaluation(
    identity: Mapping[str, Any],
    realized_garch: Mapping[str, Any],
    *,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    records = pd.DataFrame(realized_garch.get("internal_evaluation_records") or [])
    minimum = 60
    try:
        if str(realized_garch.get("status")) != "AVAILABLE" or records.empty:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="IDENTICAL_ORIGIN_QLIKE_ADAPTATION", sample_count=0, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["Realized-GARCH and baseline forecasts must share identical settled origins."])
        result = evaluate_volatility_records(records)
        conditional = _conditional_summary(result["data"], result["losses"])
        canonical = dict(canonical or {})
        cpa = canonical.get("conditional_predictive_ability") or canonical.get("research_validation_20260621") or {}
        spa = canonical.get("spa_results") or canonical.get("research_spa_results") or {}
        conditional_results = {
            "existing_conditional_predictive_ability_reused": bool(cpa),
            "existing_spa_or_reality_check_reused": bool(spa),
            "raw_average_qlike_is_not_a_promotion_gate": True,
            "conditional_qlike": conditional,
        }
        preferred = result["candidate_ranking"][0] if result["candidate_ranking"] else "UNAVAILABLE"
        # Raw ranking is shadow evidence only; no promotion occurs here.
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="QLIKE_ROBUST_PROXY_EVALUATION_ADAPTATION",
            sample_count=len(result["data"]), effective_sample_count=len(result["data"]), minimum_required_samples=minimum,
            status="AVAILABLE", score=-result["qlike_by_model"][preferred],
            confidence=min(1.0, len(result["data"]) / 500.0), reliability="SHADOW_COMPARISON",
            assumptions=["Every model is evaluated on the same chronological completed-H1 forecast origins.", "Realized variance is an imperfect but strictly positive completed-H1 proxy."],
            limitations=["Raw average QLIKE cannot promote a model without the existing CPA/SPA gates.", "Regime/session conditioning is published only when those labels are available at the forecast origin."],
            candidate_ranking=result["candidate_ranking"],
            qlike_by_model=result["qlike_by_model"],
            qlike_skill_vs_baseline=result["qlike_skill_vs_baseline"],
            variance_mse_by_model=result["variance_mse_by_model"],
            volatility_mae_by_model=result["volatility_mae_by_model"],
            median_absolute_error_by_model=result["median_absolute_error_by_model"],
            paired_loss_differences=result["paired_loss_differences"],
            conditional_results=conditional_results,
            support_count=len(result["data"]),
            preferred_shadow_volatility_method=preferred,
            promotion_enabled=False,
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=len(records),
            limitations=["A candidate is never promoted from incomparable or unresolved evaluation rows."])


__all__ = ["run_patton_evaluation", "evaluate_volatility_records"]
