"""Display-safe Buy/Sell Frequency Distribution labels for Field 1 tables.

The labels summarize already-published directional evidence.  They never replace
or mutate the protected production decision columns.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

_ALLOWED_STATES = ("Wait Pullback", "Hold and Protect", "Allowed", "No Trade")


def _decision_columns(frame: pd.DataFrame) -> list[str]:
    tokens = ("decision", "direction", "bias", "action", "pressure")
    excluded = ("correct", "source", "status", "reason", "name")
    return [
        str(column) for column in frame.columns
        if any(token in str(column).lower() for token in tokens)
        and not any(token in str(column).lower() for token in excluded)
    ]


def _score_series(frame: pd.DataFrame, side: str) -> pd.Series | None:
    side = side.upper()
    preferred = (
        f"{side} /10", f"{side}/10", f"{side} Pressure Score", f"{side} Score",
        f"{side.lower()}_score", f"{side.lower()} pressure score",
    )
    normalized = {str(c).strip().lower(): c for c in frame.columns}
    for name in preferred:
        hit = normalized.get(name.strip().lower())
        if hit is not None:
            values = pd.to_numeric(frame[hit], errors="coerce")
            if values.notna().any():
                maximum = float(values.max(skipna=True))
                return (values / (10.0 if maximum > 1.5 else 1.0)).clip(0.0, 1.0)
    return None


def _directional_fraction(frame: pd.DataFrame, side: str) -> pd.Series:
    columns = _decision_columns(frame)
    if not columns:
        return pd.Series(0.0, index=frame.index, dtype=float)
    text = frame.loc[:, columns].fillna("").astype(str).apply(lambda col: col.str.upper())
    side_hits = text.apply(lambda col: col.str.contains(side, regex=False)).sum(axis=1)
    valid = text.apply(lambda col: ~col.isin({"", "N/A", "NA", "NONE", "NAN", "MISSING", "UNAVAILABLE"})).sum(axis=1)
    return (side_hits / valid.replace(0, np.nan)).fillna(0.0).clip(0.0, 1.0)


def _rolling_frequency(values: pd.Series, window: int = 6) -> pd.Series:
    # Histories are usually newest-first.  Reverse before rolling so each row uses
    # itself and prior completed candles rather than future observations.
    chronological = values.iloc[::-1]
    rolled = chronological.rolling(window=window, min_periods=1).mean()
    return rolled.iloc[::-1].reindex(values.index).clip(0.0, 1.0)


def _current_direction(frame: pd.DataFrame) -> pd.Series:
    preferred = (
        "Final Decision", "Production Decision Raw", "Master Decision",
        "Direction Confirmation Decision", "Decision", "Direction",
    )
    for column in preferred:
        if column in frame.columns:
            return frame[column].fillna("").astype(str).str.upper()
    columns = _decision_columns(frame)
    if columns:
        return frame[columns[0]].fillna("").astype(str).str.upper()
    return pd.Series("", index=frame.index, dtype=str)


def _state_label(side_frequency: float, other_frequency: float, current: str, side: str) -> str:
    """Map evidence to a state without turning ordinary caution into No Trade.

    No Trade is reserved for genuinely absent or strongly opposing evidence.
    The older 0.62/0.42 gates were too restrictive for mixed H1 histories and
    caused both BFD and SFD to remain No Trade across almost every row.
    """
    current_text = str(current).upper()
    aligned = side in current_text
    opposing = ("SELL" if side == "BUY" else "BUY") in current_text
    dominance = side_frequency - other_frequency
    if side_frequency >= 0.52 and dominance >= 0.06 and not opposing:
        return "Allowed"
    if aligned and side_frequency >= 0.22:
        return "Hold and Protect"
    if aligned and side_frequency >= 0.05:
        return "Wait Pullback"
    if side_frequency >= 0.28 and dominance > -0.12 and not opposing:
        return "Wait Pullback"
    if side_frequency >= 0.12 and dominance >= 0.02 and not opposing:
        return "Wait Pullback"
    return "No Trade"


def enrich_bfd_sfd(frame: Any, *, window: int = 6) -> pd.DataFrame:
    """Return a copy with BFD/SFD protective-state columns.

    The function is deterministic, bounded, and uses only information already
    present in each row and earlier completed rows.
    """
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    if frame.empty:
        out = frame.copy()
        if "BFD" not in out.columns:
            out["BFD"] = pd.Series(dtype=object)
        if "SFD" not in out.columns:
            out["SFD"] = pd.Series(dtype=object)
        return out

    out = frame.copy(deep=False)
    buy_fraction = _directional_fraction(out, "BUY")
    sell_fraction = _directional_fraction(out, "SELL")
    buy_score = _score_series(out, "BUY")
    sell_score = _score_series(out, "SELL")
    if buy_score is not None:
        buy_fraction = (0.65 * buy_fraction + 0.35 * buy_score.fillna(buy_fraction)).clip(0.0, 1.0)
    if sell_score is not None:
        sell_fraction = (0.65 * sell_fraction + 0.35 * sell_score.fillna(sell_fraction)).clip(0.0, 1.0)

    bfd = _rolling_frequency(buy_fraction, window=max(2, int(window)))
    sfd = _rolling_frequency(sell_fraction, window=max(2, int(window)))
    current = _current_direction(out)

    out = out.copy()
    out["BFD"] = [
        _state_label(float(b), float(s), str(d), "BUY")
        for b, s, d in zip(bfd, sfd, current)
    ]
    out["SFD"] = [
        _state_label(float(s), float(b), str(d), "SELL")
        for b, s, d in zip(bfd, sfd, current)
    ]
    return out


def frequency_summary(frame: Any, *, window: int = 6) -> dict[str, Any]:
    enriched = enrich_bfd_sfd(frame, window=window)
    if enriched.empty:
        return {"BFD": "No Trade", "SFD": "No Trade", "rows": 0}
    row = enriched.iloc[0]
    return {
        "BFD": str(row.get("BFD") or "No Trade"),
        "SFD": str(row.get("SFD") or "No Trade"),
        "rows": int(len(enriched)),
        "allowed_states": list(_ALLOWED_STATES),
    }


__all__ = ["enrich_bfd_sfd", "frequency_summary"]
