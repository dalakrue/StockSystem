import streamlit as st

from .utils import safe_rerun


def pretrade_check_tab():
    st.markdown("# 📋 Pre-Trade Check")
    st.caption("Restored. This section was not removed.")

    items = [
        "Account Balance & Margin Checked",
        "Risk % per Trade Calculated",
        "Lot Size Verified",
        "Stop Loss & Take Profit Set",
        "Spread Acceptable",
        "No Major News / Economic Events",
        "M1 Direction Confirmed",
        "M5 Trend Alignment",
        "H1 / H4 Higher Timeframe Bias",
        "ADX Strength Valid",
        "+DI / -DI Alignment Strong",
        "Entry Candle Pattern Valid",
        "Support / Resistance Respected",
        "Volume / Liquidity OK",
        "Emotion & Psychology Clear",
        "Trading Plan Followed",
        "Internet & Platform Stable",
        "No Overtrading Signs",
        "Journal Ready to Log",
        "Exit Strategy Prepared",
    ]

    state_key = "pretrade_check_restore"

    if state_key not in st.session_state or not isinstance(st.session_state[state_key], dict):
        st.session_state[state_key] = {item: False for item in items}

    for item in items:
        if item not in st.session_state[state_key]:
            st.session_state[state_key][item] = False

    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        if st.button("🔄 Reset", use_container_width=True, key="precheck_reset"):
            st.session_state[state_key] = {item: False for item in items}
            safe_rerun()

    with c2:
        if st.button("✅ Check All", use_container_width=True, key="precheck_all"):
            st.session_state[state_key] = {item: True for item in items}
            safe_rerun()

    completed = 0

    st.divider()

    for i, item in enumerate(items):
        checked = bool(st.session_state[state_key].get(item, False))

        col1, col2 = st.columns([7, 1])

        with col1:
            icon = "✅" if checked else "⬜"
            st.markdown(f"**{icon} {item}**")

        with col2:
            if st.button(
                "ON" if checked else "OFF",
                key=f"precheck_toggle_{i}",
                use_container_width=True,
            ):
                st.session_state[state_key][item] = not checked
                safe_rerun()

        if checked:
            completed += 1

    total = len(items)
    progress = completed / total if total else 0

    st.divider()

    st.progress(progress)

    m1, m2 = st.columns(2)
    m1.metric("Progress", f"{completed}/{total}")
    m2.metric("Completion", f"{progress * 100:.1f}%")

    if completed == total:
        st.success("✅ ALL SYSTEMS GO — READY FOR HIGH-PROBABILITY ENTRY")
        st.balloons()
    elif completed >= total * 0.75:
        st.info(f"🟡 Almost ready — {total - completed} checks still pending.")
    else:
        st.warning(f"⚠️ {total - completed} checks still pending.")