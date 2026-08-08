"""Compatibility facade for split market data connectors.

The original connector API is preserved while implementation is divided into
small modules for faster maintenance and safer future upgrades.
"""
from core.connectors.data_parts.utils import (
    _connect_signature, _recent_shared_dataframe, _safe_log, _import_mt5,
    _clean_symbol, _resolve_mt5_symbol, _twelve_symbol, _normalize_ohlc,
    resample_ohlc, MT5_TIMEFRAMES, TWELVE_INTERVALS,
)
from core.connectors.data_parts.fetchers import fetch_mt5, fetch_twelve, fetch_doo_bridge
from core.connectors.data_parts.session import manual_connect, maybe_refresh, refresh_now, connect_history_60d
from core.connectors.data_parts.account import mt5_account_info, doo_bridge_account_info, get_mt5_account_snapshot

__all__ = [
    "MT5_TIMEFRAMES", "TWELVE_INTERVALS", "resample_ohlc", "fetch_mt5", "fetch_twelve",
    "fetch_doo_bridge", "manual_connect", "maybe_refresh", "refresh_now", "mt5_account_info",
    "doo_bridge_account_info", "connect_history_60d", "get_mt5_account_snapshot",
    "_normalize_ohlc", "_clean_symbol",
]
