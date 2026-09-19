import time
import pandas as pd
import requests
import streamlit as st

from core.common import synthetic_ohlc, log_event

try:
    from core.system_contract import (
        mark_data_version,
        update_connection_health,
        update_data_quality_from_session,
        record_system_event,
    )
except Exception:  # keeps old connector usable even if upgrade file is missing
    mark_data_version = None
    update_connection_health = None
    update_data_quality_from_session = None
    record_system_event = None


MT5_TIMEFRAMES = {
    "M1": "TIMEFRAME_M1",
    "M2": "TIMEFRAME_M2",
    "M3": "TIMEFRAME_M3",
    "M4": "TIMEFRAME_M4",
    "M5": "TIMEFRAME_M5",
    "M10": "TIMEFRAME_M10",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}

TWELVE_INTERVALS = {
    "M1": "1min",
    "M2": "1min",
    "M3": "1min",
    "M4": "1min",
    "M5": "5min",
    "M10": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
}




from .utils import _import_mt5

def mt5_account_info():
    mt5 = _import_mt5()

    if mt5 is None:
        return {}, False, "MT5 unavailable"

    try:
        if not mt5.initialize():
            return {}, False, "MT5 init failed"

        info = mt5.account_info()
        positions = mt5.positions_get()

        account = info._asdict() if info else {}

        pos = []
        for p in positions or []:
            try:
                pos.append(p._asdict())
            except Exception:
                pass

        account["positions"] = pos

        return account, True, "Account read ok"

    except Exception as e:
        return {}, False, str(e)

def doo_bridge_account_info(bridge_url="", bridge_token=""):
    try:
        bridge_url = str(bridge_url or "").strip()

        if not bridge_url:
            return {}, False, "Missing Doo Bridge URL"

        headers = {}

        if bridge_token:
            headers["Authorization"] = f"Bearer {bridge_token}"

        r = requests.get(
            bridge_url,
            params={"account": "1"},
            headers=headers,
            timeout=25,
        )

        try:
            data = r.json()
        except Exception:
            return {}, False, f"Doo Bridge invalid response: HTTP {r.status_code}"

        if not data.get("ok", False):
            return {}, False, str(data.get("message", data))[:250]

        account = data.get("account", {})
        positions = data.get("positions", [])

        if not isinstance(account, dict):
            account = {}

        account["positions"] = positions if isinstance(positions, list) else []

        return account, True, "Doo Bridge account read ok"

    except Exception as e:
        return {}, False, f"Doo Bridge account error: {e}"

def get_mt5_account_snapshot(bridge_url="", bridge_token=""):
    if bridge_url:
        info, ok, msg = doo_bridge_account_info(
            bridge_url=bridge_url,
            bridge_token=bridge_token,
        )
    else:
        info, ok, msg = mt5_account_info()

    positions = info.get("positions", []) if isinstance(info, dict) else []
    account = dict(info) if isinstance(info, dict) else {}
    account.pop("positions", None)

    return {
        "ok": bool(ok),
        "message": msg,
        "account": account,
        "positions": positions,
    }

