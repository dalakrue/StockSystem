"""History formatting helpers with no calculations."""
from __future__ import annotations
import pandas as pd


def newest_first(frame: pd.DataFrame, time_columns: tuple[str, ...] = ("broker_candle_time", "Broker Candle Time", "Time", "Hour"), limit: int = 25) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    output = frame.copy()
    for column in time_columns:
        if column in output.columns:
            parsed = pd.to_datetime(output[column], errors="coerce", utc=True)
            output = output.assign(_v11_sort_time=parsed).sort_values("_v11_sort_time", ascending=False).drop(columns="_v11_sort_time")
            break
    return output.head(int(limit)).reset_index(drop=True)
