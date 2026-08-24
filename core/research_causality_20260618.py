"""Reusable causal helpers for existing Research components."""
from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np
import pandas as pd


def causal_binary_target(close: pd.Series, horizon: int = 1) -> pd.Series:
    """Return 1/0 labels and preserve unknown future rows as nullable NA."""
    horizon = max(1, int(horizon))
    current = pd.to_numeric(close, errors="coerce")
    future = pd.Series(pd.NA, index=current.index, dtype="Float64")
    if len(current) > horizon:
        future.iloc[:-horizon] = current.iloc[horizon:].to_numpy()
    target = pd.Series(pd.NA, index=current.index, dtype="Int64")
    known = current.notna() & future.notna()
    target.loc[known] = (future.loc[known] > current.loc[known]).astype("int64")
    return target


def purged_time_order_split(
    frame: pd.DataFrame,
    *,
    target_col: str,
    train_fraction: float = 0.78,
    purge_rows: int = 1,
    minimum_train: int = 80,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Chronological split with a purge gap; never shuffles time-series rows."""
    if not isinstance(frame, pd.DataFrame) or target_col not in frame.columns:
        return pd.DataFrame(), pd.DataFrame()
    ordered = frame.loc[frame[target_col].notna()].copy().reset_index(drop=True)
    if ordered.empty:
        return ordered, ordered
    split = max(int(minimum_train), int(len(ordered) * float(train_fraction)))
    split = min(split, len(ordered))
    purge_rows = max(1, int(purge_rows))
    train_end = max(0, split - purge_rows)
    test_start = min(len(ordered), split + purge_rows)
    return ordered.iloc[:train_end].copy(), ordered.iloc[test_start:].copy()


def causal_news_asof(
    decisions: pd.DataFrame,
    news: pd.DataFrame,
    *,
    decision_time_col: str = "time",
    news_time_candidates: Iterable[str] = ("timestamp", "published_at", "publication_time", "time"),
) -> pd.DataFrame:
    """Backward as-of join: a decision can only see news already published."""
    if not isinstance(decisions, pd.DataFrame) or decisions.empty:
        return pd.DataFrame()
    left = decisions.copy()
    left[decision_time_col] = pd.to_datetime(left[decision_time_col], utc=True, errors="coerce")
    if not isinstance(news, pd.DataFrame) or news.empty:
        return left
    news_time_col = next((c for c in news_time_candidates if c in news.columns), None)
    if news_time_col is None:
        return left
    right = news.copy()
    right["_news_publication_time"] = pd.to_datetime(right[news_time_col], utc=True, errors="coerce")
    left = left.dropna(subset=[decision_time_col]).sort_values(decision_time_col)
    right = right.dropna(subset=["_news_publication_time"]).sort_values("_news_publication_time")
    return pd.merge_asof(
        left,
        right,
        left_on=decision_time_col,
        right_on="_news_publication_time",
        direction="backward",
        allow_exact_matches=True,
    )
