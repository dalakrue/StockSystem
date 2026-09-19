from __future__ import annotations
import pandas as pd

def build_multi_horizon_targets(frame: pd.DataFrame, close_column: str = "close", horizons=(1, 3, 6)) -> pd.DataFrame:
    out = frame.copy()
    for horizon in horizons:
        out[f"target_return_{horizon}h"] = out[close_column].shift(-horizon) / out[close_column] - 1.0
    return out
