"""Acerbi-Szekely-style Expected-Shortfall severity diagnostics in positive-loss convention."""
from __future__ import annotations

from typing import Any, Mapping
import math

import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable

METHOD_ID = "ACERBI_SZEKELY_EXPECTED_SHORTFALL_BACKTEST"
PAPER_TITLE = "Backtesting Expected Shortfall"
PAPER_AUTHORS = "Carlo Acerbi and Balazs Szekely"


def moving_block_mean_p_value(values: np.ndarray, *, replications: int = 500, block_length: int | None = None, seed: int = 20260622) -> tuple[float | None, int, float | None]:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 10:
        return None, 0, None
    std = float(np.std(x, ddof=1))
    statistic = float(math.sqrt(n) * np.mean(x) / max(std, 1e-12))
    centered = x - np.mean(x)
    block = int(block_length or max(2, round(n ** (1.0 / 3.0))))
    rng = np.random.default_rng(seed)
    starts = np.arange(n)
    need = int(math.ceil(n / block))
    boot = []
    for _ in range(int(replications)):
        idx = []
        for __ in range(need):
            start = int(rng.choice(starts))
            idx.extend((start + np.arange(block)) % n)
        sample = centered[np.asarray(idx[:n])]
        sample_std = float(np.std(sample, ddof=1))
        boot.append(float(math.sqrt(n) * np.mean(sample) / max(sample_std, 1e-12)))
    p = (1.0 + sum(v >= statistic for v in boot)) / (len(boot) + 1.0)
    return float(p), block, statistic


def expected_shortfall_backtest(
    losses: np.ndarray,
    var_forecasts: np.ndarray,
    es_forecasts: np.ndarray,
    *,
    alpha: float = 0.05,
    bootstrap_replications: int = 500,
    seed: int = 20260622,
) -> dict[str, Any]:
    loss = np.asarray(losses, dtype=float)
    var = np.asarray(var_forecasts, dtype=float)
    es = np.asarray(es_forecasts, dtype=float)
    mask = np.isfinite(loss) & np.isfinite(var) & np.isfinite(es) & (loss >= 0) & (var > 0) & (es >= var)
    loss, var, es = loss[mask], var[mask], es[mask]
    n = len(loss)
    if n < 250:
        return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": n, "minimum_required_samples": 250}
    exceptions = loss > var
    exception_count = int(exceptions.sum())
    if exception_count < max(10, int(0.5 * alpha * n)):
        return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": n, "exception_count": exception_count, "reason": "Too few VaR exceptions for ES severity inference."}
    tail_loss = loss[exceptions]
    tail_es = es[exceptions]
    residual = tail_loss / np.clip(tail_es, 1e-12, None) - 1.0
    p_value, block_length, statistic = moving_block_mean_p_value(
        residual, replications=bootstrap_replications, seed=seed
    )
    severity_under = bool(np.mean(residual) > 0.0 and p_value is not None and p_value < 0.05)
    exception_rate = float(exception_count / n)
    var_rate_warning = bool(exception_rate > alpha * 1.5)
    status = "FAIL_UNDERESTIMATED_TAIL_SEVERITY" if severity_under else ("VAR_THRESHOLD_WARNING" if var_rate_warning else "PASS")
    return {
        "status": "AVAILABLE",
        "sample_count": n,
        "exception_count": exception_count,
        "exception_rate": exception_rate,
        "predicted_ES": float(np.mean(tail_es)),
        "average_realized_tail_loss": float(np.mean(tail_loss)),
        "normalized_ES_residual": float(np.mean(residual)),
        "test_statistic": statistic,
        "bootstrap_p_value": p_value,
        "severity_underestimation": severity_under,
        "ES_backtest_status": status,
        "bootstrap_seed": int(seed),
        "block_length": int(block_length),
        "positive_loss_convention": "loss_t >= 0; VaR_t > 0; ES_t >= VaR_t. Paper P&L signs are transformed by loss_t = -P&L_t before tail comparison.",
    }


def _numeric(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    lower = {str(c).lower(): c for c in frame.columns}
    found = next((lower[n] for n in names if n in lower), None)
    return pd.to_numeric(frame[found], errors="coerce") if found is not None else None


def run_expected_shortfall_backtest(identity: Mapping[str, Any], settled: pd.DataFrame, *, bootstrap_replications: int = 500) -> dict[str, Any]:
    n = int(len(settled)) if isinstance(settled, pd.DataFrame) else 0
    minimum = 250
    try:
        if not isinstance(settled, pd.DataFrame) or settled.empty:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="POSITIVE_LOSS_ES_SEVERITY_ADAPTATION", sample_count=0, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["No settled VaR/ES outcomes were available."])
        loss = _numeric(settled, ("realized_loss", "loss", "positive_loss", "maximum_adverse_excursion"))
        var = _numeric(settled, ("predicted_var", "var", "value_at_risk", "var_forecast"))
        es = _numeric(settled, ("predicted_es", "expected_shortfall", "es", "cvar", "es_forecast"))
        if loss is None or var is None or es is None:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="POSITIVE_LOSS_ES_SEVERITY_ADAPTATION", sample_count=n, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["Existing row-level positive-loss, VaR and ES fields were not simultaneously available; no artificial ES observations were created."])
        result = expected_shortfall_backtest(loss.to_numpy(float), var.to_numpy(float), es.to_numpy(float), bootstrap_replications=bootstrap_replications)
        if result.get("status") != "AVAILABLE":
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="POSITIVE_LOSS_ES_SEVERITY_ADAPTATION", sample_count=int(result.get("sample_count") or n),
                effective_sample_count=int(result.get("exception_count") or 0), minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=[str(result.get("reason") or "At least 250 observations and adequate VaR exceptions are required.")],
                exception_count=result.get("exception_count"))
        wait_only = bool(result["severity_underestimation"])
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="DEPENDENCE_AWARE_POSITIVE_LOSS_ES_SEVERITY_BACKTEST",
            sample_count=result["sample_count"], effective_sample_count=result["exception_count"], minimum_required_samples=minimum,
            status="AVAILABLE", score=result["test_statistic"], p_value=result["bootstrap_p_value"],
            confidence=(1.0 - result["bootstrap_p_value"]) if result["bootstrap_p_value"] is not None else None,
            reliability=result["ES_backtest_status"],
            assumptions=[result["positive_loss_convention"], "The VaR threshold is pre-issued and validated before ES severity is interpreted."],
            limitations=["The diagnostic uses only existing project VaR/ES rows and never fabricates tail forecasts.", "Strong failure can only recommend WAIT or lower risk in shadow mode; it cannot increase risk."],
            exception_count=result["exception_count"], exception_rate=result["exception_rate"],
            predicted_ES=result["predicted_ES"], average_realized_tail_loss=result["average_realized_tail_loss"],
            normalized_ES_residual=result["normalized_ES_residual"], test_statistic=result["test_statistic"],
            bootstrap_p_value=result["bootstrap_p_value"], severity_underestimation=result["severity_underestimation"],
            ES_backtest_status=result["ES_backtest_status"], bootstrap_seed=result["bootstrap_seed"],
            block_length=result["block_length"], shadow_wait_only_risk_recommendation=wait_only,
            risk_multiplier_increase_allowed=False,
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["Tail-risk evidence fails safely and can never increase the protected risk multiplier."])


__all__ = ["run_expected_shortfall_backtest", "expected_shortfall_backtest", "moving_block_mean_p_value"]
