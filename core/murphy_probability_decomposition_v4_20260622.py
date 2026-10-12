"""Murphy Brier-score decomposition for settled probabilistic events."""
from __future__ import annotations

from typing import Any, Mapping
import numpy as np
import pandas as pd

from core.quant_research_v4_contract_20260622 import common_result, unavailable

METHOD_ID = "MURPHY_BRIER_DECOMPOSITION"
PAPER_TITLE = "A New Vector Partition of the Probability Score"
PAPER_AUTHORS = "Allan H. Murphy"


def adaptive_reliability_bins(probabilities: np.ndarray, outcomes: np.ndarray, *, max_bins: int = 20, min_bin_support: int = 20) -> list[dict[str, Any]]:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y) & (p >= 0) & (p <= 1) & ((y == 0) | (y == 1))
    p, y = p[mask], y[mask]
    if len(p) == 0:
        return []
    order = np.argsort(p, kind="mergesort")
    p, y = p[order], y[order]
    target_bins = max(1, min(max_bins, len(p) // max(1, min_bin_support)))
    chunks = np.array_split(np.arange(len(p)), target_bins)
    bins = []
    for idx in chunks:
        if len(idx) == 0:
            continue
        bins.append({
            "count": int(len(idx)),
            "min_probability": float(p[idx].min()),
            "max_probability": float(p[idx].max()),
            "mean_forecast_probability": float(p[idx].mean()),
            "empirical_event_rate": float(y[idx].mean()),
        })
    # Sparse neighboring bins are deterministically merged.
    merged: list[dict[str, Any]] = []
    for item in bins:
        if merged and (item["count"] < min_bin_support or merged[-1]["count"] < min_bin_support):
            prev = merged.pop()
            n1, n2 = prev["count"], item["count"]
            total = n1 + n2
            merged.append({
                "count": total,
                "min_probability": min(prev["min_probability"], item["min_probability"]),
                "max_probability": max(prev["max_probability"], item["max_probability"]),
                "mean_forecast_probability": (prev["mean_forecast_probability"] * n1 + item["mean_forecast_probability"] * n2) / total,
                "empirical_event_rate": (prev["empirical_event_rate"] * n1 + item["empirical_event_rate"] * n2) / total,
            })
        else:
            merged.append(item)
    return merged


def murphy_decomposition(probabilities: np.ndarray, outcomes: np.ndarray, *, max_bins: int = 20, min_bin_support: int = 20) -> dict[str, Any]:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y) & (p >= 0) & (p <= 1) & ((y == 0) | (y == 1))
    p, y = p[mask], y[mask]
    if len(p) < max(30, min_bin_support * 2):
        raise ValueError("Insufficient settled probabilistic observations.")
    bins = adaptive_reliability_bins(p, y, max_bins=max_bins, min_bin_support=min_bin_support)
    base = float(y.mean())
    n = float(len(y))
    reliability = sum((b["count"] / n) * (b["mean_forecast_probability"] - b["empirical_event_rate"]) ** 2 for b in bins)
    resolution = sum((b["count"] / n) * (b["empirical_event_rate"] - base) ** 2 for b in bins)
    uncertainty = base * (1.0 - base)
    brier = float(np.mean((p - y) ** 2))
    reconstructed = float(reliability - resolution + uncertainty)
    climatology = float(np.mean((base - y) ** 2))
    skill = float(1.0 - brier / climatology) if climatology > 1e-12 else None
    return {
        "brier_score": brier,
        "reliability_component": float(reliability),
        "resolution_component": float(resolution),
        "uncertainty_component": float(uncertainty),
        "brier_skill_score": skill,
        "reliability_bins": bins,
        "reconstructed_brier_score": reconstructed,
        "decomposition_residual": float(brier - reconstructed),
        "sample_count": int(len(y)),
        "event_rate": base,
    }


def _numeric(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    lower = {str(c).lower(): c for c in frame.columns}
    found = next((lower[n] for n in names if n in lower), None)
    return pd.to_numeric(frame[found], errors="coerce") if found is not None else None


def _event_specs(settled: pd.DataFrame) -> list[tuple[str, str, pd.Series, pd.Series, str]]:
    specs: list[tuple[str, str, pd.Series, pd.Series, str]] = []
    direction_y = _numeric(settled, ("direction_correct", "direction_hit", "correct_direction"))
    direction_p = _numeric(settled, ("direction_probability", "direction_confidence", "confidence", "forecast_confidence", "reliability"))
    if direction_y is not None and direction_p is not None:
        if direction_p.max(skipna=True) > 1.0:
            direction_p = direction_p / 100.0
        specs.append(("directional_correctness", "Predicted direction equals settled target direction", direction_p, direction_y, "direction correctness"))

    direct_tp = _numeric(settled, ("tp_before_sl", "tp_first", "target_before_stop"))
    tp_p = _numeric(settled, ("tp_first_probability", "target_probability", "tp_probability"))
    if direct_tp is not None and tp_p is not None:
        if tp_p.max(skipna=True) > 1.0:
            tp_p = tp_p / 100.0
        specs.append(("tp_before_sl", "TP is reached before SL", tp_p, direct_tp, "TP-before-SL"))
    else:
        target = _numeric(settled, ("target_hit", "tp_hit", "take_profit_hit"))
        stop = _numeric(settled, ("stop_hit", "sl_hit", "stop_loss_hit"))
        if target is not None and stop is not None and tp_p is not None:
            valid = ((target == 1) & (stop != 1)) | ((target != 1) & (stop == 1))
            specs.append(("tp_before_sl", "TP is reached before SL", tp_p, ((target == 1) & (stop != 1)).astype(float).where(valid), "TP-before-SL"))

    interval_y = _numeric(settled, ("interval_hit", "coverage_flag", "inside_interval"))
    interval_p = _numeric(settled, ("nominal_coverage", "interval_coverage_probability", "interval_probability", "coverage_probability"))
    if interval_y is not None and interval_p is not None:
        if interval_p.max(skipna=True) > 1.0:
            interval_p = interval_p / 100.0
        specs.append(("interval_hit", "Settled price lies inside the pre-issued interval", interval_p, interval_y, "interval hit"))

    continuation_y = _numeric(settled, ("regime_continued", "regime_continuation_outcome", "same_regime_at_target"))
    continuation_p = _numeric(settled, ("regime_continuation_probability", "continuation_probability", "regime_probability"))
    if continuation_y is not None and continuation_p is not None:
        if continuation_p.max(skipna=True) > 1.0:
            continuation_p = continuation_p / 100.0
        specs.append(("regime_continuation", "Protected regime label remains unchanged through the settled horizon", continuation_p, continuation_y, "regime continuation"))

    trade_y = _numeric(settled, ("tradeable_outcome", "protected_tradeable_correct", "tradeable_decision_correct"))
    trade_p = _numeric(settled, ("tradeable_probability", "tradeability_probability", "decision_confidence"))
    if trade_y is not None and trade_p is not None:
        if trade_p.max(skipna=True) > 1.0:
            trade_p = trade_p / 100.0
        specs.append(("protected_tradeable_decision", "Protected tradeable decision succeeds under the recorded event definition", trade_p, trade_y, "protected tradeable decision"))

    bull_p = _numeric(settled, ("bull_probability", "buy_probability"))
    lower = {str(c).lower(): c for c in settled.columns}
    actual_col = next((lower[n] for n in ("actual_direction", "settled_direction", "target_direction") if n in lower), None)
    if bull_p is not None and actual_col is not None:
        if bull_p.max(skipna=True) > 1.0:
            bull_p = bull_p / 100.0
        raw = settled[actual_col]
        numeric = pd.to_numeric(raw, errors="coerce")
        text = raw.astype(str).str.strip().str.upper()
        buy = pd.Series(np.nan, index=settled.index, dtype=float)
        buy.loc[text.isin(["BUY", "UP", "BULL", "LONG", "1", "+1"])] = 1.0
        buy.loc[text.isin(["SELL", "DOWN", "BEAR", "SHORT", "-1", "0"])] = 0.0
        if numeric.notna().any():
            buy.loc[numeric > 0] = 1.0
            buy.loc[numeric < 0] = 0.0
            if not (numeric < 0).any():
                buy.loc[numeric == 0] = 0.0
        specs.append(("buy_probability", "Settled direction is BUY", bull_p, buy, "BUY event"))
        specs.append(("sell_probability", "Settled direction is SELL", 1.0 - bull_p, 1.0 - buy, "SELL event"))
    return specs


def run_murphy_decomposition(identity: Mapping[str, Any], settled: pd.DataFrame) -> dict[str, Any]:
    n = int(len(settled)) if isinstance(settled, pd.DataFrame) else 0
    minimum = 60
    try:
        if not isinstance(settled, pd.DataFrame) or settled.empty:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="ADAPTIVE_BIN_DECOMPOSITION", sample_count=0, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["No settled probabilistic outcomes were available."])
        horizons = sorted(set(pd.to_numeric(settled.get("horizon_hours", pd.Series([1] * len(settled))), errors="coerce").fillna(1).astype(int)))
        output: dict[str, Any] = {}
        total_support = 0
        for event_id, definition, probabilities, outcomes, label in _event_specs(settled):
            event_result = {"event_definition": definition, "horizons": {}}
            for horizon in horizons:
                mask = pd.to_numeric(settled.get("horizon_hours", pd.Series([1] * len(settled))), errors="coerce").fillna(1).astype(int) == horizon
                p = probabilities.loc[mask].to_numpy(float)
                y = outcomes.loc[mask].to_numpy(float)
                try:
                    dec = murphy_decomposition(p, y, max_bins=20, min_bin_support=10)
                    over = dec["reliability_component"] > max(0.02, dec["uncertainty_component"] * 0.20) and np.nanmean(p) > np.nanmean(y) + 0.05
                    under = dec["reliability_component"] > max(0.02, dec["uncertainty_component"] * 0.20) and np.nanmean(p) < np.nanmean(y) - 0.05
                    weak = dec["resolution_component"] < max(0.005, dec["uncertainty_component"] * 0.05)
                    dec.update({"overconfidence_warning": bool(over), "underconfidence_warning": bool(under), "weak_resolution_warning": bool(weak)})
                    event_result["horizons"][str(horizon)] = dec
                    total_support += dec["sample_count"]
                except Exception as exc:
                    event_result["horizons"][str(horizon)] = {"status": "INSUFFICIENT_EVIDENCE", "error": str(exc), "sample_count": int(mask.sum())}
            output[event_id] = event_result
        if not output:
            return common_result(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
                exact_or_adaptation="ADAPTIVE_BIN_DECOMPOSITION", sample_count=n, minimum_required_samples=minimum,
                status="INSUFFICIENT_EVIDENCE", limitations=["No supported event had both a pre-issued probability and settled binary outcome."])
        available = [d for e in output.values() for d in e["horizons"].values() if d.get("brier_score") is not None]
        status = "AVAILABLE" if available else "INSUFFICIENT_EVIDENCE"
        worst_reliability = max((d["reliability_component"] for d in available), default=None)
        return common_result(
            identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            exact_or_adaptation="ADAPTIVE_SUPPORT_MERGED_MURPHY_DECOMPOSITION",
            sample_count=n, effective_sample_count=total_support, minimum_required_samples=minimum,
            status=status, score=(1.0 - worst_reliability) if worst_reliability is not None else None,
            confidence=min(1.0, total_support / 500.0), reliability="EVENT_AND_HORIZON_SPECIFIC",
            assumptions=["Each probability is issued before its settled binary event.", "BUY and SELL are evaluated as separately documented events."],
            limitations=["Adaptive-bin decomposition can have a small finite-bin reconstruction residual.", "Sparse neighboring bins are merged and unsupported horizons remain INSUFFICIENT_EVIDENCE."],
            events=output,
            supported_event_count=len(available),
            overall_overconfidence_warning=any(d.get("overconfidence_warning") for d in available),
            overall_underconfidence_warning=any(d.get("underconfidence_warning") for d in available),
            overall_weak_resolution_warning=any(d.get("weak_resolution_warning") for d in available),
        )
    except Exception as exc:
        return unavailable(identity, method_id=METHOD_ID, paper_title=PAPER_TITLE, paper_authors=PAPER_AUTHORS,
            error=exc, minimum_required_samples=minimum, sample_count=n,
            limitations=["Unsupported probabilities are never replaced by invented probabilities."])


__all__ = ["run_murphy_decomposition", "murphy_decomposition", "adaptive_reliability_bins"]
