"""Synthetic OHLC fallback data used only when safe demo mode is enabled."""

import pandas as pd
import numpy as np

from core.utils.numeric import safe_int


def synthetic_ohlc(symbol="XAUUSD", bars=1500):
    bars = max(50, safe_int(bars, 1500))
    symbol = str(symbol or "XAUUSD").upper()
    rng = np.random.default_rng(abs(hash(symbol)) % (2**32))

    if "XAU" in symbol:
        base, scale = 2350, 0.70
    elif "JPY" in symbol:
        base, scale = 150, 0.025
    elif "EUR" in symbol:
        base, scale = 1.08, 0.00025
    elif "GBP" in symbol:
        base, scale = 1.27, 0.00035
    elif "BTC" in symbol:
        base, scale = 65000, 40
    elif "ETH" in symbol:
        base, scale = 3500, 5
    else:
        base, scale = 100, 0.10

    steps = rng.normal(0, scale, bars).cumsum()
    close = base + steps
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, scale * 0.5, bars))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, scale * 0.5, bars))
    volume = rng.integers(100, 3000, size=bars)

    return pd.DataFrame(
        {
            "time": pd.date_range(end=pd.Timestamp.now(), periods=int(bars), freq="min"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
