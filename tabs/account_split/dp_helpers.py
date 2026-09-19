# Future-upgrade split module.
# Safe helper re-exports from unchanged implementation.

try:
    from .implementation import (
        _safe_num,
        _safe_int,
        _safe_text,
        _safe_append_csv,
        _safe_read_csv,
        _safe_rerun,
        _safe_log_event,
        _safe_close_sidebar,
        _normalize_account_info,
        _safe_mt5_account_info,
        _safe_manual_connect,
        _safe_quant_stack,
        _save_once_per_60_seconds,
    )
except Exception:
    import streamlit as st
    import pandas as pd
    import numpy as np

    def _safe_num(v, default=0.0):
        try:
            if v is None or (isinstance(v, str) and v.strip() == ''):
                return default
            v = float(v)
            return v if np.isfinite(v) else default
        except Exception:
            return default

    def _safe_int(v, default=0):
        try:
            return int(v)
        except Exception:
            return default

    def _safe_text(v, default=''):
        try:
            return default if v is None else str(v)
        except Exception:
            return default

    def _safe_append_csv(name, row):
        return False, 'append_csv unavailable.'

    def _safe_read_csv(name):
        return pd.DataFrame()

    def _safe_rerun():
        try:
            st.rerun()
        except Exception:
            pass

    def _safe_log_event(message):
        return None

    def _safe_close_sidebar():
        return None

    def _normalize_account_info(raw):
        if isinstance(raw, dict):
            return raw, bool(raw.get('ok', True)), raw.get('message', 'OK')
        return {}, False, 'Unsupported MT5 account response.'

    def _safe_mt5_account_info():
        return {}, False, 'mt5_account_info unavailable.'

    def _safe_manual_connect(*args, **kwargs):
        st.error('manual_connect unavailable.')

    def _safe_quant_stack(df):
        return {'bias': 'WAIT', 'scale10': 0, 'safe_pct': 0}

    def _save_once_per_60_seconds(name, row, state_key):
        return False, 'CSV save unavailable.'

__all__ = [
    '_safe_num', '_safe_int', '_safe_text', '_safe_append_csv', '_safe_read_csv',
    '_safe_rerun', '_safe_log_event', '_safe_close_sidebar', '_normalize_account_info',
    '_safe_mt5_account_info', '_safe_manual_connect', '_safe_quant_stack',
    '_save_once_per_60_seconds',
]
