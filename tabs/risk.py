import streamlit as st
import pandas as pd

from core.database import append_csv, read_csv


# ============================================================
# SAFE HELPERS
# ============================================================

def _safe_read_csv(name: str) -> pd.DataFrame:
    try:
        df = read_csv(name)
        if df is None:
            return pd.DataFrame()
        return df
    except Exception as e:
        st.warning(f"Could not read {name}: {e}")
        return pd.DataFrame()


def _safe_append_csv(name: str, row: dict) -> bool:
    try:
        append_csv(name, row)
        return True
    except Exception as e:
        st.error(f"Could not save {name}: {e}")
        return False


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_div(numerator, denominator, default: float = 0.0) -> float:
    try:
        numerator = float(numerator)
        denominator = float(denominator)
        if denominator == 0:
            return default
        return numerator / denominator
    except Exception:
        return default


def _now() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def _risk_color_status(risk_pct: float, margin_level: float) -> str:
    risk_pct = _safe_float(risk_pct)
    margin_level = _safe_float(margin_level)

    if risk_pct <= 1 and margin_level >= 300:
        return "🟢 Safe"
    if risk_pct <= 2 and margin_level >= 150:
        return "🟡 Medium"
    return "🔴 High Risk"


def _account_snapshot() -> dict:
    info = st.session_state.get("account_snapshot", {})
    return info if isinstance(info, dict) else {}


# ============================================================
# MAIN TAB
# ============================================================

def show():
    st.markdown("# 🛡️ Risk Tab — Original + Doo Prime Account Inner Tabs")

    t1, t2, t3, t4 = st.tabs([
        "Original Risk Calculator",
        "Doo Prime Risk",
        "Risk History",
        "Advanced Risk Check",
    ])

    # ========================================================
    # TAB 1 — ORIGINAL RISK CALCULATOR
    # ========================================================
    with t1:
        st.subheader("Original Risk Calculator")

        c1, c2 = st.columns(2)

        with c1:
            balance = st.number_input(
                "Balance",
                min_value=0.0,
                value=float(st.session_state.get("risk_balance", 1000.0)),
                step=50.0,
                key="risk_balance",
            )

            risk = st.slider(
                "Risk %",
                min_value=0.1,
                max_value=10.0,
                value=float(st.session_state.get("risk_percent", 1.0)),
                step=0.1,
                key="risk_percent",
            )

        with c2:
            sl = st.number_input(
                "Stop loss pips",
                min_value=0.0,
                value=float(st.session_state.get("risk_sl_pips", 50.0)),
                step=1.0,
                key="risk_sl_pips",
            )

            pip_value = st.number_input(
                "Pip value per 1 lot",
                min_value=0.0,
                value=float(st.session_state.get("risk_pip_value", 10.0)),
                step=0.1,
                key="risk_pip_value",
            )

        dollar_risk = balance * risk / 100
        lot = _safe_div(dollar_risk, sl * pip_value, 0.0)

        c = st.columns(4)
        c[0].metric("Suggested Lot", round(lot, 3))
        c[1].metric("Dollar Risk", round(dollar_risk, 2))
        c[2].metric("Stop Loss Pips", round(sl, 2))
        c[3].metric("Risk %", round(risk, 2))

        if sl <= 0:
            st.warning("Stop loss must be greater than 0.")
        if pip_value <= 0:
            st.warning("Pip value must be greater than 0.")

        note = st.text_input("Optional plan note", key="risk_plan_note")

        if st.button("💾 Save Risk Plan", key="save_risk_plan", use_container_width=True):
            row = {
                "time": _now(),
                "balance": balance,
                "risk_pct": risk,
                "sl_pips": sl,
                "pip_value": pip_value,
                "dollar_risk": dollar_risk,
                "lot": lot,
                "note": note,
            }

            if _safe_append_csv("risk_plans", row):
                st.success("Saved risk plan")

    # ========================================================
    # TAB 2 — DOO PRIME ACCOUNT RISK
    # ========================================================
    with t2:
        st.subheader("Doo Prime Account Risk")

        info = _account_snapshot()

        if not info:
            st.info("Read Doo Prime account inside Home first.")
        else:
            bal = _safe_float(info.get("balance", 0))
            eq = _safe_float(info.get("equity", 0))
            free = _safe_float(info.get("margin_free", info.get("free_margin", 0)))
            ml = _safe_float(info.get("margin_level", info.get("margin_level_percent", 0)))
            margin = _safe_float(info.get("margin", 0))
            profit = _safe_float(info.get("profit", 0))

            free_margin_ratio = _safe_div(free, eq, 0.0) * 100
            equity_gap = eq - bal

            c = st.columns(4)
            c[0].metric("Balance", round(bal, 2))
            c[1].metric("Equity", round(eq, 2))
            c[2].metric("Free Margin", round(free, 2))
            c[3].metric("Margin Level %", round(ml, 2))

            c2 = st.columns(4)
            c2[0].metric("Used Margin", round(margin, 2))
            c2[1].metric("Floating P/L", round(profit, 2))
            c2[2].metric("Equity - Balance", round(equity_gap, 2))
            c2[3].metric("Free Margin Ratio", round(free_margin_ratio, 2))

            danger_equity_floor = eq * 0.10
            loss_room = max(0, eq - danger_equity_floor)
            danger_buffer = max(0, free - danger_equity_floor)

            current_risk = st.session_state.get("risk_percent", 1.0)
            account_status = _risk_color_status(current_risk, ml)

            st.metric("Estimated Loss Room Before Danger", round(loss_room, 2))
            st.metric("Danger Buffer", round(danger_buffer, 2))
            st.markdown(f"### Account Status: {account_status}")

            if ml > 0 and ml < 100:
                st.error("Margin level is dangerous. Avoid new trades.")
            elif ml > 0 and ml < 150:
                st.warning("Margin level is weak. Reduce exposure.")
            elif ml >= 300:
                st.success("Margin level looks healthy.")
            elif ml == 0:
                st.info("Margin level is 0 or unavailable.")

            if st.button("💾 Save Doo Prime Risk Snapshot", key="save_doo_risk", use_container_width=True):
                row = {
                    "time": _now(),
                    "balance": bal,
                    "equity": eq,
                    "free_margin": free,
                    "margin_level": ml,
                    "used_margin": margin,
                    "floating_profit": profit,
                    "equity_gap": equity_gap,
                    "free_margin_ratio": free_margin_ratio,
                    "loss_room": loss_room,
                    "danger_buffer": danger_buffer,
                    "status": account_status,
                }

                if _safe_append_csv("risk_snapshots", row):
                    st.success("Doo Prime risk snapshot saved")

    # ========================================================
    # TAB 3 — RISK HISTORY
    # ========================================================
    with t3:
        st.subheader("Risk History")

        risk_df = _safe_read_csv("risk_plans")
        snap_df = _safe_read_csv("risk_snapshots")
        adv_df = _safe_read_csv("advanced_risk_checks")

        h1, h2, h3 = st.tabs([
            "Risk Plans",
            "Doo Prime Snapshots",
            "Advanced Checks",
        ])

        with h1:
            if risk_df.empty:
                st.info("No saved risk plans yet.")
            else:
                st.dataframe(risk_df.tail(300), use_container_width=True)

        with h2:
            if snap_df.empty:
                st.info("No saved Doo Prime risk snapshots yet.")
            else:
                st.dataframe(snap_df.tail(300), use_container_width=True)

        with h3:
            if adv_df.empty:
                st.info("No saved advanced risk checks yet.")
            else:
                st.dataframe(adv_df.tail(300), use_container_width=True)

    # ========================================================
    # TAB 4 — ADVANCED RISK CHECK
    # ========================================================
    with t4:
        st.subheader("Advanced Risk Check")

        balance2 = st.number_input(
            "Advanced Balance",
            min_value=0.0,
            value=float(st.session_state.get("risk_balance", 1000.0)),
            step=50.0,
            key="adv_balance",
        )

        open_trades = st.number_input(
            "Open Trades Count",
            min_value=0,
            value=0,
            step=1,
            key="adv_open_trades",
        )

        risk_per_trade = st.slider(
            "Risk Per Trade %",
            min_value=0.1,
            max_value=10.0,
            value=float(st.session_state.get("risk_percent", 1.0)),
            step=0.1,
            key="adv_risk_trade",
        )

        max_daily_loss = st.slider(
            "Max Daily Loss %",
            min_value=1.0,
            max_value=30.0,
            value=5.0,
            step=0.5,
            key="adv_daily_loss",
        )

        total_open_risk = open_trades * risk_per_trade
        daily_loss_amount = balance2 * max_daily_loss / 100
        one_trade_loss = balance2 * risk_per_trade / 100

        max_slots = int(max_daily_loss // risk_per_trade) if risk_per_trade > 0 else 0
        remaining_slots = max(0, max_slots - open_trades)

        c = st.columns(4)
        c[0].metric("One Trade Risk $", round(one_trade_loss, 2))
        c[1].metric("Total Open Risk %", round(total_open_risk, 2))
        c[2].metric("Max Daily Loss $", round(daily_loss_amount, 2))
        c[3].metric("Remaining Trade Slots", remaining_slots)

        if total_open_risk >= max_daily_loss:
            st.error("Open risk is already at or above your daily loss limit. Do not add new trades.")
        elif total_open_risk >= max_daily_loss * 0.7:
            st.warning("Open risk is near your daily limit. Use smaller size or wait.")
        else:
            st.success("Risk level is acceptable.")

        if st.button("💾 Save Advanced Risk Check", key="save_advanced_risk", use_container_width=True):
            row = {
                "time": _now(),
                "balance": balance2,
                "open_trades": open_trades,
                "risk_per_trade": risk_per_trade,
                "max_daily_loss": max_daily_loss,
                "total_open_risk": total_open_risk,
                "daily_loss_amount": daily_loss_amount,
                "one_trade_loss": one_trade_loss,
                "remaining_slots": remaining_slots,
            }

            if _safe_append_csv("advanced_risk_checks", row):
                st.success("Advanced risk check saved")