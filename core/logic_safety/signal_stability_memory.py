"""Signal Stability Memory."""
from __future__ import annotations
from typing import Any, Dict
from ._shared import normalize_ohlc, clamp


def calculate(df: Any, metrics: Dict[str, Any]) -> Dict[str, Any]:
    x = normalize_ohlc(df)
    if x is None or len(x) < 12 or "close" not in x.columns:
        return {"label": "Mixed", "stability_score": 55.0, "flip_count_3h": 0, "flip_count_6h": 0, "flip_count_12h": 0, "main_instability_source": "Not enough history loaded"}
    try:
        import numpy as np
        close = x["close"].astype(float)
        direction = np.sign(close.diff().fillna(0))
        direction = direction.mask(direction == 0).ffill().fillna(0)
        def flips(n: int) -> int:
            s = direction.tail(n)
            return int((s != s.shift(1)).sum() - 1) if len(s) > 1 else 0
        f3, f6, f12 = flips(3), flips(6), flips(12)
        penalty = f3 * 8 + f6 * 5 + f12 * 3
        stability = clamp(100 - penalty, 0, 100, 60)
        label = "Stable" if stability >= 75 else "Mixed" if stability >= 50 else "Unstable"
        return {"label": label, "stability_score": round(stability, 1), "flip_count_3h": f3, "flip_count_6h": f6, "flip_count_12h": f12, "direction_stability": label, "priority_stability": "Partial — priority history not required", "regime_stability": "Measured separately", "main_instability_source": "Direction flipped too often" if label == "Unstable" else "No severe signal flip detected"}
    except Exception as exc:
        return {"label": "Mixed", "stability_score": 55.0, "flip_count_3h": 0, "flip_count_6h": 0, "flip_count_12h": 0, "main_instability_source": str(exc)[:140]}
