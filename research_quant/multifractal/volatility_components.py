from __future__ import annotations
import numpy as np
import pandas as pd


def volatility_components(returns, *, annualization: float = 1.0) -> dict[str, float]:
    values = pd.Series(returns, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return {name: float("nan") for name in ("immediate", "session", "daily", "persistent", "jump", "residual")}
    def safe_std(window: int) -> float:
        sample = values.tail(window)
        return float(sample.std(ddof=0)) if len(sample) >= 2 else 0.0
    immediate = safe_std(6)
    session = safe_std(24)
    daily = safe_std(48)
    persistent_series = values.ewm(span=min(120, max(2, len(values))), adjust=False).std(bias=True)
    persistent = float(persistent_series.iloc[-1]) if len(values) >= 2 and pd.notna(persistent_series.iloc[-1]) else daily
    threshold = 3.0 * max(daily, 1e-12)
    jump = float(values[values.abs() > threshold].abs().mean()) if (values.abs() > threshold).any() else 0.0
    combined_known = np.sqrt(np.nanmean(np.square([immediate, session, daily, persistent])))
    overall = float(values.std(ddof=0)) if len(values) >= 2 else 0.0
    residual = float(max(0.0, overall - combined_known))
    scale = float(np.sqrt(annualization))
    return {"immediate": immediate * scale, "session": session * scale, "daily": daily * scale, "persistent": persistent * scale, "jump": jump * scale, "residual": residual * scale}
