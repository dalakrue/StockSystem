"""Shared Candle After Regime Start column helpers.

The value is the existing saved Hamilton-regime age measured in completed
candles.  These helpers expose it consistently without fitting, fetching, or
changing any protected regime calculation.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
from pandas.io.formats.style import Styler

CANDLE_AGE_COLUMN = "Candle After Regime Start"
REGIME_START_STANDARD_COLUMN = "Regime Start Standard"
REGIME_START_AGE_RANK_COLUMN = "Regime Start Age Rank"
RECENT_CHANGE_RANK_COLUMN = "Recent Regime Change Rank"
STANDARD_AGE_COLUMNS = {
    "LOWER": "Lower Candle After Regime Start",
    "MIDDLE": "Middle Candle After Regime Start",
    "HIGHER": "Higher Candle After Regime Start",
}


def _clean_age(value: Any) -> float:
    try:
        number = float(value)
    except Exception:
        return float("nan")
    if not np.isfinite(number) or number < 0:
        return float("nan")
    return float(int(round(number)))


def _standard(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {"LOW": "LOWER", "MEDIUM": "MIDDLE", "MID": "MIDDLE", "HIGH": "HIGHER"}
    return aliases.get(text, text)


def evidence_age_map(evidence: Any) -> dict[tuple[str, str], float]:
    """Return {(SYMBOL, STANDARD): completed-candle age} from saved evidence."""
    if not isinstance(evidence, pd.DataFrame) or evidence.empty:
        return {}
    symbol_col = "Symbol" if "Symbol" in evidence.columns else "symbol" if "symbol" in evidence.columns else None
    standard_col = "Standard" if "Standard" in evidence.columns else "standard" if "standard" in evidence.columns else None
    age_col = next((c for c in (CANDLE_AGE_COLUMN, "Regime Age", "regime_age") if c in evidence.columns), None)
    if not symbol_col or not standard_col or not age_col:
        return {}
    out: dict[tuple[str, str], float] = {}
    for _, row in evidence.iterrows():
        symbol = str(row.get(symbol_col) or "").strip().upper()
        standard = _standard(row.get(standard_col))
        age = _clean_age(row.get(age_col))
        if symbol and standard in STANDARD_AGE_COLUMNS and np.isfinite(age):
            out[(symbol, standard)] = age
    return out


def enrich_evidence(evidence: Any) -> pd.DataFrame:
    """Add the requested display column to each standard-evidence row."""
    if not isinstance(evidence, pd.DataFrame):
        return pd.DataFrame()
    frame = evidence.copy()
    source = next((c for c in (CANDLE_AGE_COLUMN, "Regime Age", "regime_age") if c in frame.columns), None)
    if source:
        frame[CANDLE_AGE_COLUMN] = pd.to_numeric(frame[source], errors="coerce").round().astype("Int64")
    elif CANDLE_AGE_COLUMN not in frame.columns:
        frame[CANDLE_AGE_COLUMN] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    return frame


def enrich_ranking(ranking: Any, evidence: Any) -> pd.DataFrame:
    """Expose standard ages and a final dominant-standard age on ranking rows.

    ``Candle After Regime Start`` in the final ranking uses the row's existing
    Dominant Standard.  The two additional ranks remove ambiguity:
    age rank 1 = regime started earliest/has lasted longest; recent-change rank
    1 = regime changed most recently.
    """
    if not isinstance(ranking, pd.DataFrame):
        return pd.DataFrame()
    frame = ranking.copy()
    ages = evidence_age_map(evidence)
    symbols = frame.get("Symbol", pd.Series("", index=frame.index)).astype(str).str.upper()
    for standard, column in STANDARD_AGE_COLUMNS.items():
        if column not in frame.columns:
            frame[column] = [ages.get((symbol, standard), float("nan")) for symbol in symbols]
        frame[column] = pd.to_numeric(frame[column], errors="coerce").round().astype("Int64")

    def final_age(row: pd.Series) -> tuple[Any, str]:
        dominant = _standard(row.get("Dominant Standard"))
        if dominant not in STANDARD_AGE_COLUMNS:
            dominant = "HIGHER"
        value = row.get(STANDARD_AGE_COLUMNS[dominant])
        if pd.isna(value):
            for fallback in ("HIGHER", "MIDDLE", "LOWER"):
                candidate = row.get(STANDARD_AGE_COLUMNS[fallback])
                if not pd.isna(candidate):
                    return candidate, fallback
            return pd.NA, dominant
        return value, dominant

    final_values = frame.apply(final_age, axis=1)
    frame[CANDLE_AGE_COLUMN] = pd.Series([v[0] for v in final_values], index=frame.index, dtype="Int64")
    frame[REGIME_START_STANDARD_COLUMN] = [v[1] for v in final_values]
    numeric = pd.to_numeric(frame[CANDLE_AGE_COLUMN], errors="coerce")
    frame[REGIME_START_AGE_RANK_COLUMN] = numeric.rank(method="min", ascending=False, na_option="bottom").astype("Int64")
    frame[RECENT_CHANGE_RANK_COLUMN] = numeric.rank(method="min", ascending=True, na_option="bottom").astype("Int64")
    return frame


def add_age_alias_to_table(data: Any, *, fallback_age: Any = None) -> Any:
    """Add the canonical regime-age column to compatible tables.

    Non-tabular objects and pandas Styler instances are returned unchanged.
    """
    if isinstance(data, Styler):
        return data
    if isinstance(data, pd.Series):
        frame = data.to_frame().T
    elif isinstance(data, pd.DataFrame):
        frame = data.copy()
    elif isinstance(data, (list, tuple)) and data and isinstance(data[0], Mapping):
        frame = pd.DataFrame(data)
    else:
        return data
    if CANDLE_AGE_COLUMN in frame.columns:
        return frame
    source = next((c for c in ("Regime Age", "regime_age", "Age", "age") if c in frame.columns), None)
    if source:
        frame[CANDLE_AGE_COLUMN] = pd.to_numeric(frame[source], errors="coerce").round().astype("Int64")
    elif fallback_age is not None:
        age = _clean_age(fallback_age)
        frame[CANDLE_AGE_COLUMN] = pd.Series(
            [int(age) if np.isfinite(age) else pd.NA] * len(frame), index=frame.index, dtype="Int64"
        )
    return frame


__all__ = [
    "CANDLE_AGE_COLUMN", "REGIME_START_STANDARD_COLUMN", "REGIME_START_AGE_RANK_COLUMN",
    "RECENT_CHANGE_RANK_COLUMN", "STANDARD_AGE_COLUMNS", "evidence_age_map",
    "enrich_evidence", "enrich_ranking", "add_age_alias_to_table",
]
