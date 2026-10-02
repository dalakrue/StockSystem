import pandas as pd
import streamlit as st

from .constants import DATA_KEY, SOURCE_KEY, SYMBOL_KEY, TF_KEY, RESULT_KEY, SUMMARY_KEY
from .utils import safe_rerun, get_secret_or_env
from .symbols import mt5_symbol, twelve_symbol
from .data import normalize_ohlc, resample_m2_m3, load_twelve, load_mt5, make_demo_data
from .history_engine import find_similar_days


def _safe_num(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _save_loaded_data(df, source, symbol, tf):
    st.session_state[DATA_KEY] = df
    st.session_state[SOURCE_KEY] = source
    st.session_state[SYMBOL_KEY] = symbol
    st.session_state[TF_KEY] = tf
    st.session_state.pop(RESULT_KEY, None)
    st.session_state.pop(SUMMARY_KEY, None)


def _clear_history_state():
    for k in [DATA_KEY, SOURCE_KEY, SYMBOL_KEY, TF_KEY, RESULT_KEY, SUMMARY_KEY]:
        st.session_state.pop(k, None)


def _load_data_source(source, symbol, tf, scan_bars, api_key="", csv_file=None, demo_days=130):
    df = pd.DataFrame()
    err = ""
    final_symbol = symbol

    try:
        if source == "Twelve Data":
            df, err = load_twelve(symbol, tf, int(scan_bars), api_key)
            final_symbol = twelve_symbol(symbol)

        elif source == "MT5":
            df, err = load_mt5(symbol, tf, int(scan_bars))
            final_symbol = mt5_symbol(symbol)

        elif source == "CSV Upload":
            final_symbol = "CSV"
            if csv_file is None:
                return pd.DataFrame(), "Please upload CSV first.", final_symbol

            df = pd.read_csv(csv_file)
            df = normalize_ohlc(df)
            df = resample_m2_m3(df, tf)

        elif source == "Session last_df":
            final_symbol = "Session last_df"
            session_df = st.session_state.get("last_df")

            if session_df is None:
                return pd.DataFrame(), "Session last_df is missing.", final_symbol

            df = normalize_ohlc(session_df)
            df = resample_m2_m3(df, tf)

            if df.empty:
                err = "Session last_df is empty after cleaning."

        else:
            df = make_demo_data(symbol=symbol, tf=tf, days=int(demo_days), seed=12)
            final_symbol = f"Demo {symbol}"

    except Exception as exc:
        df = pd.DataFrame()
        err = f"{source} failed: {exc}"

    return df, err, final_symbol


def advanced_history_tab():
    st.markdown("# 🧠 Advanced History Matching")
    st.caption(
        "Find historical days with similar recent candle behavior. "
        "This is pattern matching, not full strategy backtesting."
    )

    st.markdown("## 🔌 Load Data")

    source = st.radio(
        "Data Source",
        ["Twelve Data", "MT5", "CSV Upload", "Session last_df", "Demo Data"],
        horizontal=True,
        key="pre_src",
    )

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        default_symbol = "XAU/USD" if source == "Twelve Data" else "XAUUSD"
        
        try:
            from core.global_symbol_context import get_global_symbol_context
            symbol = get_global_symbol_context(st.session_state).active_display_symbol
        except Exception:
            symbol = ""
        st.caption(f"Global Symbol: {symbol or 'NOT PUBLISHED'} (read-only)")

    with c2:
        tf = st.selectbox(
            "Timeframe",
            ["M1", "M2", "M3", "M5", "M15", "M30", "H1", "H4", "D1"],
            index=1,
            key="pre_tf",
        )

    with c3:
        lookback_days = st.number_input(
            "Lookback Days",
            min_value=10,
            max_value=250,
            value=100,
            step=5,
            key="pre_lookback_days",
        )

    with c4:
        top_n = st.number_input(
            "Top Result Days",
            min_value=5,
            max_value=50,
            value=10,
            step=1,
            key="pre_top_days",
        )

    c5, c6, c7 = st.columns(3)

    with c5:
        pattern_window = st.number_input(
            "Pattern Candles",
            min_value=60,
            max_value=300,
            value=120,
            step=10,
            key="pre_pattern_window",
        )

    with c6:
        future_horizon = st.number_input(
            "Future Move Candles",
            min_value=30,
            max_value=720,
            value=120,
            step=30,
            key="pre_future_horizon",
        )

    with c7:
        scan_bars = st.number_input(
            "Candles To Load",
            min_value=500,
            max_value=150000,
            value=90000 if source in ["MT5", "Demo Data"] else 5000,
            step=500,
            key="pre_candles_to_load",
        )

    api_key = ""
    csv_file = None
    demo_days = int(max(lookback_days + 30, 130))

    if source == "Twelve Data":
        default_key = get_secret_or_env("TWELVE_API_KEY", "TWELVE_DATA_API_KEY", default="")
        api_key = st.text_input(
            "Twelve Data API Key",
            value=default_key,
            type="password",
            key="pre_td_key",
        )
        st.caption(
            "Twelve free/limited plans may return only limited candles. "
            "For deep M1/M2/M3 history, MT5 or CSV is better."
        )

    if source == "CSV Upload":
        csv_file = st.file_uploader(
            "Upload CSV with time/open/high/low/close",
            type=["csv"],
            key="pre_csv",
        )

    if source == "Demo Data":
        demo_days = st.slider("Demo Days", 30, 250, demo_days, 5, key="pre_demo_days")

    col_load, col_clear = st.columns(2)

    with col_load:
        load_clicked = st.button(
            "🚀 Load Data",
            type="primary",
            use_container_width=True,
            key="pre_load_data",
        )

    with col_clear:
        clear_clicked = st.button(
            "🧹 Clear Loaded Data",
            use_container_width=True,
            key="pre_clear_data",
        )

    if clear_clicked:
        _clear_history_state()
        safe_rerun()

    if load_clicked:
        with st.spinner("Loading history data..."):
            df, err, final_symbol = _load_data_source(
                source=source,
                symbol=symbol,
                tf=tf,
                scan_bars=int(scan_bars),
                api_key=api_key,
                csv_file=csv_file,
                demo_days=int(demo_days),
            )

        if err:
            if "MetaTrader5" in err or "MT5" in err:
                st.warning(err)
                st.info(
                    "MT5 requires local Windows MetaTrader 5 terminal and "
                    "`pip install MetaTrader5`. Use Twelve Data, CSV, or Demo Data if MT5 is unavailable."
                )
            else:
                st.error(err)
            return

        if not isinstance(df, pd.DataFrame) or df.empty:
            st.error("Loaded data is empty.")
            return

        try:
            df = normalize_ohlc(df)
            df = resample_m2_m3(df, tf)
        except Exception as exc:
            st.error(f"Loaded data could not be normalized: {exc}")
            return

        if df.empty:
            st.error("Data became empty after cleaning/resampling.")
            return

        _save_loaded_data(df, source, final_symbol, tf)
        st.success(f"Loaded {len(df):,} candles from {source}")
        safe_rerun()

    df = st.session_state.get(DATA_KEY)

    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info("Load data first. For quick test, choose **Demo Data** and click **Load Data**.")
        return

    try:
        clean = normalize_ohlc(df)
        clean = resample_m2_m3(clean, st.session_state.get(TF_KEY, tf))
    except Exception as exc:
        st.error(f"Loaded data invalid: {exc}")
        return

    if clean.empty:
        st.error("Cleaned data is empty.")
        return

    source_loaded = st.session_state.get(SOURCE_KEY, "Unknown")
    symbol_loaded = st.session_state.get(SYMBOL_KEY, "Unknown")
    tf_loaded = st.session_state.get(TF_KEY, "Unknown")

    st.success(
        f"Connected: {source_loaded} | {symbol_loaded} | {tf_loaded} | "
        f"Candles: {len(clean):,}"
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Candles", f"{len(clean):,}")
    m2.metric("From", str(clean["time"].iloc[0]))
    m3.metric("To", str(clean["time"].iloc[-1]))
    m4.metric("Last Close", f"{_safe_num(clean['close'].iloc[-1]):.5f}")

    min_required = int(pattern_window) + int(future_horizon) + 20

    if len(clean) < min_required:
        st.warning(
            f"Not enough candles. Need at least {min_required:,}, "
            f"but only have {len(clean):,}."
        )
        return

    run = st.button(
        "🧠 Find Similar Days",
        type="primary",
        use_container_width=True,
        key="pre_run_similarity",
    )

    if run:
        with st.spinner("Finding similar days and ranking them..."):
            try:
                result, summary = find_similar_days(
                    clean,
                    lookback_days=int(lookback_days),
                    window=int(pattern_window),
                    horizon=int(future_horizon),
                    top_n=int(top_n),
                    mc_paths=300,
                )
            except TypeError:
                result, summary = find_similar_days(
                    clean,
                    lookback_days=int(lookback_days),
                    window=int(pattern_window),
                    horizon=int(future_horizon),
                    top_n=int(top_n),
                )
            except Exception as exc:
                st.error(f"History matching failed: {exc}")
                return

        if not isinstance(result, pd.DataFrame) or result.empty:
            if isinstance(summary, dict):
                st.warning(summary.get("Status", "No result."))
            else:
                st.warning("No similar day result found.")
            return

        if not isinstance(summary, dict):
            summary = {}

        st.session_state[RESULT_KEY] = result
        st.session_state[SUMMARY_KEY] = summary

    result = st.session_state.get(RESULT_KEY)
    summary = st.session_state.get(SUMMARY_KEY)

    if isinstance(result, pd.DataFrame) and not result.empty:
        if not isinstance(summary, dict):
            summary = {}

        st.markdown("## ✅ Similar Day Ranking")

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Dominant Bias", summary.get("Dominant Bias", "N/A"))
        s2.metric("Bullish %", summary.get("Bullish %", 0))
        s3.metric("Bearish %", summary.get("Bearish %", 0))
        s4.metric("Top Score", round(_safe_num(summary.get("Top Score", 0)), 2))

        st.info(
            f"Current window end: {summary.get('Current Window End', 'N/A')} | "
            f"Search: {summary.get('Search', 'N/A')} | "
            f"Returned days: {summary.get('Returned Days', len(result))}"
        )

        if len(result) < int(top_n):
            st.warning(
                f"Only {len(result)} non-duplicate days found. "
                f"To get {top_n}+ days, load more candles/history."
            )

        with st.expander("📊 Open history match result table", expanded=False):
            st.dataframe(result, use_container_width=True, height=520)

        st.markdown("## ⬇️ Lowest Ranked In Returned Result")

        sort_col = "Final Rank Score"
        if sort_col in result.columns:
            low_df = result.sort_values(sort_col, ascending=True)
        else:
            low_df = result.tail(min(len(result), 10))

        with st.expander("📉 Open low-score history table", expanded=False):
            st.dataframe(low_df, use_container_width=True, height=260)

        st.caption("⬇️ Similar-day CSV export is centralized in the sidebar Download Center. Result data remains visible above.")
