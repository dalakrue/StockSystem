def mt5_symbol(symbol):
    raw = str(symbol or "XAUUSD").strip().upper()
    return raw.replace("/", "").replace(" ", "")


def twelve_symbol(symbol):
    raw = str(symbol or "XAU/USD").strip().upper()
    raw_clean = raw.replace(" ", "")

    mapping = {
        "XAUUSD": "XAU/USD",
        "XAU/USD": "XAU/USD",
        "XAGUSD": "XAG/USD",
        "XAG/USD": "XAG/USD",
        "EURUSD": "EUR/USD",
        "EUR/USD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "GBP/USD": "GBP/USD",
        "USDJPY": "USD/JPY",
        "USD/JPY": "USD/JPY",
        "AUDUSD": "AUD/USD",
        "AUD/USD": "AUD/USD",
        "USDCAD": "USD/CAD",
        "USD/CAD": "USD/CAD",
        "USDCHF": "USD/CHF",
        "USD/CHF": "USD/CHF",
        "NZDUSD": "NZD/USD",
        "NZD/USD": "NZD/USD",
        "BTCUSD": "BTC/USD",
        "BTC/USD": "BTC/USD",
        "ETHUSD": "ETH/USD",
        "ETH/USD": "ETH/USD",
    }

    return mapping.get(raw_clean, raw)


def timeframe_minutes(tf):
    tf = str(tf or "M1").strip().upper()

    return {
        "M1": 1,
        "1M": 1,
        "M2": 2,
        "2M": 2,
        "M3": 3,
        "3M": 3,
        "M5": 5,
        "5M": 5,
        "M15": 15,
        "15M": 15,
        "M30": 30,
        "30M": 30,
        "H1": 60,
        "1H": 60,
        "H4": 240,
        "4H": 240,
        "D1": 1440,
        "1D": 1440,
    }.get(tf, 1)


def twelve_interval(tf):
    tf = str(tf or "M1").strip().upper()

    return {
        "M1": "1min",
        "1M": "1min",
        "M2": "1min",
        "2M": "1min",
        "M3": "1min",
        "3M": "1min",
        "M5": "5min",
        "5M": "5min",
        "M15": "15min",
        "15M": "15min",
        "M30": "30min",
        "30M": "30min",
        "H1": "1h",
        "1H": "1h",
        "H4": "4h",
        "4H": "4h",
        "D1": "1day",
        "1D": "1day",
    }.get(tf, "1min")