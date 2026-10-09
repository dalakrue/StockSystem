import pandas as pd
import streamlit as st


def sync_backtest_keys_from_last_df():
    """Make the original backtest tab see the shared Engine data.
    This does not edit the original backtest code.
    It only fills the session keys that the original backtest tab already uses.
    """
    df = st.session_state.get("last_df")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return False

    symbol = st.session_state.get("symbol", "XAUUSD")
    source = st.session_state.get("source", "SHARED_ENGINE")

    st.session_state["combined_original_backtest_raw_df"] = df
    st.session_state["combined_original_backtest_source"] = source
    st.session_state["combined_original_backtest_symbol"] = symbol
    st.session_state["combined_original_backtest_last_load"] = pd.Timestamp.now()

    # Keep old result until user reruns backtest. Do not delete user's saved result automatically.
    return True


def shared_data_status():
    df = st.session_state.get("last_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        return True, len(df)
    return False, 0
