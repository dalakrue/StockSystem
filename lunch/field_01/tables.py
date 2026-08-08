from __future__ import annotations
import pandas as pd


def filter_table(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    mask = frame.astype(str).apply(lambda column: column.str.contains(query, case=False, na=False)).any(axis=1)
    return frame.loc[mask].reset_index(drop=True)
