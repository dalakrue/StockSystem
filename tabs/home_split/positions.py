# Future-upgrade split module.
# Safe re-export functions from the unchanged original implementation.
# This file will NOT affect original code. It only imports existing functions
# and provides safe fallbacks/new analytics helpers if implementation is missing.

import pandas as pd
import numpy as np


# ==========================================================
# SAFE IMPORT FROM ORIGINAL IMPLEMENTATION
# ==========================================================

try:
    from .implementation import (
        _position_to_dict,
        _guess_pip_size,
        _calc_pips,
        _positions_frame,
    )
except Exception:

    def _position_to_dict(pos):
        if isinstance(pos, dict):
            return pos

        if hasattr(pos, "_asdict"):
            try:
                return pos._asdict()
            except Exception:
                pass

        try:
            return dict(pos)
        except Exception:
            pass

        out = {}
        for key in dir(pos):
            if key.startswith("_"):
                continue
            try:
                value = getattr(pos, key)
                if not callable(value):
                    out[key] = value
            except Exception:
                pass
        return out


    def _safe_num(v, default=0.0):
        try:
            if v is None:
                return default
            v = float(v)
            if not np.isfinite(v):
                return default
            return v
        except Exception:
            return default


    def _guess_pip_size(symbol, price=None):
        symbol = str(symbol or "").upper()
        price = _safe_num(price)

        if "JPY" in symbol:
            return 0.01
        if "XAU" in symbol or "GOLD" in symbol:
            return 0.1
        if "XAG" in symbol or "SILVER" in symbol:
            return 0.01
        if "BTC" in symbol or "ETH" in symbol:
            return 1.0
        if price >= 100:
            return 0.01
        return 0.0001


    def _calc_pips(row):
        price_open = _safe_num(row.get("price_open"))
        price_current = _safe_num(row.get("price_current"))
        symbol = row.get("symbol", "")
        side = str(row.get("side", "")).upper()

        if price_open <= 0 or price_current <= 0:
            return 0.0

        pip_size = _guess_pip_size(symbol, price_open)

        if side == "SELL":
            pips = (price_open - price_current) / pip_size
        else:
            pips = (price_current - price_open) / pip_size

        return round(pips, 1)


    def _positions_frame(info):
        positions = info.get("positions", []) if isinstance(info, dict) else []

        if not positions:
            return pd.DataFrame()

        rows = [_position_to_dict(p) for p in positions]
        df = pd.DataFrame(rows)

        if df.empty:
            return pd.DataFrame()

        if "time" in df.columns:
            df["open_time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")

        for c in ["profit", "volume", "price_open", "price_current", "swap", "commission"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

        if "type" in df.columns:
            df["side"] = df["type"].map({0: "BUY", 1: "SELL"}).fillna(df["type"].astype(str))
        elif "side" not in df.columns:
            df["side"] = "UNKNOWN"

        if "price_open" in df.columns and "price_current" in df.columns:
            df["pips"] = df.apply(_calc_pips, axis=1)

        return df


# ==========================================================
# NEW SAFE POSITION ANALYTICS
# ==========================================================

def position_profit_summary(info):
    """
    New helper.
    Returns BUY/SELL P/L, profit/loss combinations, and exposure summary.
    Safe for Doo Prime / MT5 account snapshot.
    """
    df = _positions_frame(info)

    if df.empty or "profit" not in df.columns:
        return {
            "buy_pl": 0.0,
            "sell_pl": 0.0,
            "total_profit_positions": 0.0,
            "total_loss_positions": 0.0,
            "net_pl": 0.0,
            "profit_count": 0,
            "loss_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "total_positions": 0,
            "status": "NO DATA",
            "meaning": "No open MT5 positions found.",
            "frame": df,
        }

    side = df.get("side", pd.Series(["UNKNOWN"] * len(df))).astype(str).str.upper()
    profit = pd.to_numeric(df["profit"], errors="coerce").fillna(0)

    buy_pl = float(profit[side == "BUY"].sum())
    sell_pl = float(profit[side == "SELL"].sum())
    total_profit = float(profit[profit > 0].sum())
    total_loss = float(profit[profit < 0].sum())
    net_pl = float(profit.sum())

    if net_pl > 0:
        status = "GOOD"
        meaning = "Open position combination is net profitable."
    elif net_pl < 0:
        status = "BAD"
        meaning = "Open position combination is net losing."
    else:
        status = "NEUTRAL"
        meaning = "Open position combination is flat."

    return {
        "buy_pl": round(buy_pl, 2),
        "sell_pl": round(sell_pl, 2),
        "total_profit_positions": round(total_profit, 2),
        "total_loss_positions": round(total_loss, 2),
        "net_pl": round(net_pl, 2),
        "profit_count": int((profit > 0).sum()),
        "loss_count": int((profit < 0).sum()),
        "buy_count": int((side == "BUY").sum()),
        "sell_count": int((side == "SELL").sum()),
        "total_positions": int(len(df)),
        "status": status,
        "meaning": meaning,
        "frame": df,
    }


__all__ = [
    "_position_to_dict",
    "_guess_pip_size",
    "_calc_pips",
    "_positions_frame",
    "position_profit_summary",
]