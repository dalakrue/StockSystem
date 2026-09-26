"""Authoritative fixed 20-symbol FX universe for StratLit.

All multi-symbol loading, Super Quick calculations, and Finder history are
restricted to this list.  Keeping the boundary in one small module prevents
stale saved selector state (for example XAUUSD) from leaking into provider
requests or historical results.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

TARGET_FX_SYMBOLS: tuple[str, ...] = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
    "CHFJPY", "EURAUD", "EURCAD", "EURCHF", "EURGBP",
    "EURJPY", "EURNZD", "EURUSD", "GBPJPY", "GBPUSD",
    "NZDCAD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
)
FIRST_TARGET_10: tuple[str, ...] = TARGET_FX_SYMBOLS[:10]
SECOND_TARGET_10: tuple[str, ...] = TARGET_FX_SYMBOLS[10:]
TARGET_FX_SET = frozenset(TARGET_FX_SYMBOLS)


def normalize_fx_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def filter_target_symbols(values: Any, *, limit: int | None = None) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence):
        values = []
    result: list[str] = []
    for value in values:
        symbol = normalize_fx_symbol(value)
        if symbol in TARGET_FX_SET and symbol not in result:
            result.append(symbol)
        if limit is not None and len(result) >= max(0, int(limit)):
            break
    return result


def fixed_groups() -> dict[str, list[str]]:
    return {
        "FIRST": list(FIRST_TARGET_10),
        "SECOND": list(SECOND_TARGET_10),
        "THIRD": [],
    }


__all__ = [
    "TARGET_FX_SYMBOLS", "FIRST_TARGET_10", "SECOND_TARGET_10", "TARGET_FX_SET",
    "normalize_fx_symbol", "filter_target_symbols", "fixed_groups",
]
