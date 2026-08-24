import streamlit as st
import pandas as pd

from core.quant_models import quant_stack, add_indicators
from core.database import read_csv, append_csv


# ============================================================
# SAFE HELPERS
# ============================================================

def _safe_read_csv(name):
    try:
        df = read_csv(name)
        if df is None:
            return pd.DataFrame()
        if not isinstance(df, pd.DataFrame):
            return pd.DataFrame()
        return df
    except Exception as e:
        st.warning(f"Could not read {name}: {e}")
        return pd.DataFrame()


def _safe_append_csv(name, row):
    try:
        append_csv(name, row)
        return True
    except Exception as e:
        st.error(f"Could not save {name}: {e}")
        return False


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _now():
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_add_indicators(df):
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()

        out = add_indicators(df.copy())

        if out is None or not isinstance(out, pd.DataFrame):
            return df.copy()

        return out

    except Exception as e:
        st.error(f"Indicator calculation failed: {e}")
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _safe_quant_stack(df, hist, account_snapshot):
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return {
                "bias": "WAIT",
                "scale10": 0,
                "safe_pct": 0,
                "history_samples": len(hist),
                "error": "No valid dataframe found",
            }

        if not isinstance(hist, list):
            hist = []

        if not isinstance(account_snapshot, dict):
            account_snapshot = {}

        q = quant_stack(df.copy(), hist, account_snapshot)

        if not isinstance(q, dict):
            return {
                "bias": "WAIT",
                "scale10": 0,
                "safe_pct": 0,
                "history_samples": len(hist),
                "error": "quant_stack did not return dict",
            }

        q.setdefault("bias", "WAIT")
        q.setdefault("scale10", 0)
        q.setdefault("safe_pct", 0)
        q.setdefault("history_samples", len(hist))

        return q

    except Exception as e:
        return {
            "bias": "WAIT",
            "scale10": 0,
            "safe_pct": 0,
            "history_samples": len(hist) if isinstance(hist, list) else 0,
            "error": str(e),
        }


def _clean_for_save(q):
    row = {}

    if not isinstance(q, dict):
        return row

    for k, v in q.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            row[k] = v
        else:
            row[k] = str(v)

    return row


def _build_history():
    hist = []

    backtest_df = _safe_read_csv("backtest_results")
    if not backtest_df.empty:
        hist.extend(backtest_df.to_dict("records"))

    training_df = _safe_read_csv("training_data")
    if not training_df.empty:
        hist.extend(training_df.to_dict("records"))

    session_hist = st.session_state.get("trade_history", [])
    if isinstance(session_hist, list):
        hist.extend(session_hist)

    return hist


def _get_last_df():
    df = st.session_state.get("last_df")

    if isinstance(df, pd.DataFrame) and not df.empty:
        return df.copy()

    fallback_df = _safe_read_csv("latest_market_data")
    if isinstance(fallback_df, pd.DataFrame) and not fallback_df.empty:
        return fallback_df.copy()

    return pd.DataFrame()


def _bias_status(bias):
    bias = str(bias).upper()

    if "BUY" in bias:
        return "🟢 BUY SIDE"
    if "SELL" in bias:
        return "🔴 SELL SIDE"
    return "🟡 WAIT / NEUTRAL"


# ============================================================
# MAIN TAB
# ============================================================

def show():
    st.markdown("# 🧠 Mix — Advanced History Matching")

    df = _get_last_df()

    if df.empty:
        st.warning(
            "Connect data from Home or Engine first. Mix will use persistent data and will not blank until disconnect."
        )
        return

    hist = _build_history()

    account_snapshot = st.session_state.get("account_snapshot", {})
    if not isinstance(account_snapshot, dict):
        account_snapshot = {}

    feature_df = _safe_add_indicators(df)
    q = _safe_quant_stack(feature_df, hist, account_snapshot)

    bias = q.get("bias", "WAIT")
    scale10 = _safe_float(q.get("scale10", 0))
    safe_pct = _safe_float(q.get("safe_pct", 0))
    history_samples = _safe_int(q.get("history_samples", len(hist)))

    st.markdown("## Current Mix Decision")

    c = st.columns(4)
    c[0].metric("Best Safe Bias", bias)
    c[1].metric("Scale /10", round(scale10, 2))
    c[2].metric("Safe Percent", round(safe_pct, 2))
    c[3].metric("History Samples", history_samples)

    st.markdown(f"### Status: {_bias_status(bias)}")

    if "error" in q:
        st.error(f"Mix engine fallback mode: {q['error']}")

    if scale10 >= 7:
        st.success("Strong setup detected.")
    elif scale10 >= 4:
        st.warning("Medium setup. Confirm with market structure.")
    else:
        st.info("Weak setup. Waiting is safer.")

    # ========================================================
    # ACCOUNT SNAPSHOT
    # ========================================================

    with st.expander("Account Snapshot Used By Mix", expanded=False):
        if account_snapshot:
            st.json(account_snapshot)
        else:
            st.info("No account snapshot available yet.")

    # ========================================================
    # FULL OUTPUT
    # ========================================================

    with st.expander("Full Mix Engine Output", expanded=True):
        st.json(q)

    # ========================================================
    # SAVE DECISION
    # ========================================================

    st.markdown("## Save Decision")

    save_note = st.text_input("Optional note", key="mix_save_note")

    c_save1, c_save2 = st.columns(2)

    with c_save1:
        if st.button("💾 Save Mix Decision To Training Data", key="save_mix_training", use_container_width=True):
            row = {
                "time": _now(),
                "tab": "mix",
                "note": save_note,
                "rows_used": len(feature_df),
                **_clean_for_save(q),
            }

            if _safe_append_csv("training_data", row):
                st.success("Saved to training_data")

    with c_save2:
        if st.button("💾 Save Mix Decision To Mix History", key="save_mix_history", use_container_width=True):
            row = {
                "time": _now(),
                "tab": "mix",
                "note": save_note,
                "rows_used": len(feature_df),
                **_clean_for_save(q),
            }

            if _safe_append_csv("mix_history", row):
                st.success("Saved to mix_history")

    # ========================================================
    # LATEST FEATURE DATA
    # ========================================================

    st.markdown("## Latest Feature Data")

    if feature_df.empty:
        st.warning("No feature data available.")
    else:
        max_rows = min(500, len(feature_df))
        min_rows = 1 if max_rows < 20 else 20
        default_rows = min(60, max_rows)

        row_count = st.slider(
            "Rows to show",
            min_value=min_rows,
            max_value=max_rows,
            value=default_rows,
            key="mix_rows_to_show",
        )

        st.dataframe(feature_df.tail(row_count), use_container_width=True)

        st.caption("⬇️ Latest feature export is centralized in the sidebar Download Center.")

    # ========================================================
    # MIX HISTORY VIEW
    # ========================================================

    st.markdown("## Saved Mix History")

    mix_history_df = _safe_read_csv("mix_history")

    if mix_history_df.empty:
        st.info("No saved mix history yet.")
    else:
        st.dataframe(mix_history_df.tail(200), use_container_width=True)