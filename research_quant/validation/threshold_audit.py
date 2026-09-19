"""Leakage-safe shadow comparison for decision thresholds.

This module never changes Table 4.  It evaluates candidate thresholds only
when settled outcome columns exist; otherwise it emits an explicit
INSUFFICIENT_DATA row for every candidate.
"""
from __future__ import annotations

from typing import Iterable
import numpy as np
import pandas as pd

from research_quant.validation.cpcv import combinatorial_purged_splits
from research_quant.validation.pbo import probability_of_backtest_overfitting
from research_quant.validation.purging import information_intervals


def _decision(score: pd.Series, threshold: float) -> pd.Series:
    values = pd.to_numeric(score, errors="coerce")
    return pd.Series(np.where(values >= threshold, "BUY", np.where(values <= -threshold, "SELL", "WAIT")), index=score.index)


def _utility(decision: pd.Series, outcome: pd.Series, cost: float) -> float:
    sign = decision.map({"BUY": 1.0, "SELL": -1.0, "WAIT": 0.0}).fillna(0.0)
    realized = pd.to_numeric(outcome, errors="coerce").fillna(0.0)
    turnover = sign.diff().abs().fillna(sign.abs())
    return float((sign * realized - cost * turnover).mean())


def audit_thresholds(
    frame: pd.DataFrame,
    *,
    score_column: str,
    outcome_column: str | None,
    time_column: str,
    current_threshold: float,
    candidate_multipliers: Iterable[float] = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5),
    embargo_candles: int = 6,
    transaction_cost: float = 0.0,
) -> pd.DataFrame:
    columns = [
        "Current Threshold", "Research Candidate Threshold", "CPCV Result", "PBO",
        "Expected Utility", "Decision Turnover", "False BUY Rate", "False SELL Rate",
        "WAIT Rate", "WAIT PULLBACK Rate", "HOLD Rate", "Promotion Status", "Reason",
    ]
    if not isinstance(frame, pd.DataFrame) or frame.empty or score_column not in frame or time_column not in frame:
        return pd.DataFrame([{**{column: None for column in columns}, "Current Threshold": current_threshold,
                              "Promotion Status": "RESEARCH_ONLY", "Reason": "INSUFFICIENT_DATA"}])
    work = frame.copy().sort_values(time_column).reset_index(drop=True)
    work[time_column] = pd.to_datetime(work[time_column], errors="coerce", utc=True)
    work = work.dropna(subset=[time_column, score_column])
    settled = outcome_column is not None and outcome_column in work and pd.to_numeric(work[outcome_column], errors="coerce").notna().sum() >= 30
    rows: list[dict] = []
    for multiplier in candidate_multipliers:
        candidate = abs(float(current_threshold) * float(multiplier))
        decisions = _decision(work[score_column], candidate)
        row = {
            "Current Threshold": current_threshold,
            "Research Candidate Threshold": candidate,
            "CPCV Result": "INSUFFICIENT_SETTLED_OUTCOMES",
            "PBO": None, "Expected Utility": None,
            "Decision Turnover": float((decisions != decisions.shift()).mean()),
            "False BUY Rate": None, "False SELL Rate": None,
            "WAIT Rate": float((decisions == "WAIT").mean()),
            "WAIT PULLBACK Rate": 0.0, "HOLD Rate": 0.0,
            "Promotion Status": "RESEARCH_ONLY",
            "Reason": "Candidate is shadow-only; production threshold is unchanged.",
        }
        if settled:
            outcome = pd.to_numeric(work[outcome_column], errors="coerce")
            intervals = information_intervals(work[time_column], work[time_column].shift(-1).fillna(work[time_column]))
            if len(intervals) == len(work) and len(work) >= 36:
                n_groups = min(6, max(3, len(work) // 10))
                paths = list(combinatorial_purged_splits(intervals, n_groups=n_groups, test_groups_per_split=1, embargo_candles=embargo_candles))
                in_scores, out_scores = [], []
                for split in paths:
                    train_decision = decisions.iloc[split.train_indices]
                    test_decision = decisions.iloc[split.test_indices]
                    in_scores.append(_utility(train_decision, outcome.iloc[split.train_indices], transaction_cost))
                    out_scores.append(_utility(test_decision, outcome.iloc[split.test_indices], transaction_cost))
                if paths:
                    # PBO needs candidate matrices. With one candidate, report
                    # path stability but keep promotion blocked rather than
                    # manufacturing a competitive rank.
                    row["CPCV Result"] = f"{len(paths)} leakage-safe paths; competitive PBO requires >=2 candidates in one run"
                    row["Expected Utility"] = float(np.mean(out_scores))
                    row["PBO"] = None
            signs = outcome.apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
            row["False BUY Rate"] = float(((decisions == "BUY") & (signs <= 0)).sum() / max(1, (decisions == "BUY").sum()))
            row["False SELL Rate"] = float(((decisions == "SELL") & (signs >= 0)).sum() / max(1, (decisions == "SELL").sum()))
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)
