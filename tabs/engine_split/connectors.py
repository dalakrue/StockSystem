from core.global_symbol_compat import set_legacy_calculation_symbol
import pandas as pd
import streamlit as st

try:
    from core.data_connectors import manual_connect
except Exception:
    manual_connect = None


def safe_connect(source, symbol, api_key, bars=5000, timeframe="M1"):
    """Shared connector for the combined Engine tab.
    It does not replace your original connector functions.
    It only calls core.data_connectors.manual_connect and stores data in session_state.
    """
    if manual_connect is None:
        st.error("manual_connect is unavailable. Check core.data_connectors.py")
        return False

    try:
        with st.spinner(f"Connecting {source.upper()} {symbol} {timeframe}..."):
            try:
                manual_connect(source, symbol, api_key, bars=int(bars), timeframe=timeframe)
            except TypeError:
                manual_connect(source, symbol, api_key, bars=int(bars))

        df = st.session_state.get("last_df")
        if not isinstance(df, pd.DataFrame) or df.empty:
            st.error("Connector finished, but st.session_state['last_df'] is empty.")
            return False

        st.session_state["connected"] = True
        st.session_state["source"] = str(source).upper()
        set_legacy_calculation_symbol(st.session_state, symbol, connector=True)
        st.session_state["timeframe"] = timeframe
        st.session_state["engine_shared_rows"] = len(df)
        st.success(f"{source.upper()} loaded {len(df):,} candles for {symbol} {timeframe}.")
        return True

    except Exception as exc:
        st.error(f"{source.upper()} connection failed: {exc}")
        return False
