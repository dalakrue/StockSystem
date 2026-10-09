"""Symbol normalization helpers."""


def normalize_symbol(symbol="XAUUSD"):
    symbol = str(symbol or "XAUUSD").strip().upper()
    return symbol.replace(" ", "").replace("/", "")
