"""Dedicated read-only Morning Quant Control renderer for V8.

This module never calculates, fetches, retrains, recalibrates or republishes a
canonical generation. It renders only the last Settings-published result.
"""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
import streamlit as st

HISTORY_TABLES = {
    "Account State": "morning_account_state_history",
    "Position & Exposure": "morning_position_exposure_history",
    "Risk Budget & Stress": "morning_risk_budget_stress_history",
    "Forecast & Outcome": "morning_forecast_outcome_history",
    "Execution & API Health": "morning_execution_api_health_history",
    "Clock & Synchronization Audit": "clock_sync_audit_history",
}


def _canonical() -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(st.session_state)
        if isinstance(value, Mapping): return value
    except Exception: pass
    for key in ("canonical_decision_result", "canonical_decision_result_20260617", "canonical_result_20260617"):
        value = st.session_state.get(key)
        if isinstance(value, Mapping): return value
    return {}


def _m(value: Any) -> Mapping[str, Any]: return value if isinstance(value, Mapping) else {}


def _display(value: Any, *, digits: int = 2, suffix: str = "") -> str:
    if value is None or value == "": return "UNAVAILABLE"
    try: return f"{float(value):,.{digits}f}{suffix}"
    except Exception: return str(value)


@st.cache_data(show_spinner=False, max_entries=64, ttl=300)
def _cached_history(table: str, search: str, limit: int, calculation_id: str, generation_id: str, logic_version: str) -> pd.DataFrame:
    """Immutable bounded history query keyed by published canonical identity."""
    del calculation_id, generation_id, logic_version
    from core.morning_quant_store_20260622 import query_history
    return query_history(table, search=search, limit=limit)


def _metric_grid(items: list[tuple[str, Any, str]]) -> None:
    for start in range(0, len(items), 4):
        cols = st.columns(min(4, len(items)-start))
        for col, (label, value, help_text) in zip(cols, items[start:start+4]):
            col.metric(label, _display(value))
            if value is None and help_text: col.caption(help_text)


def _render_overview(v8: Mapping[str, Any]) -> None:
    morning = _m(v8.get("morning")); account = _m(morning.get("account")); exposure = _m(morning.get("exposure")); dd = _m(morning.get("drawdown")); risk = _m(morning.get("risk_budget")); stress = _m(morning.get("stress")); es95 = _m(morning.get("expected_shortfall_95")); es99 = _m(morning.get("expected_shortfall_99")); clock = _m(v8.get("broker_time_contract")); readiness = _m(v8.get("readiness")); execution = _m(morning.get("execution_health"))
    _metric_grid([
        ("Balance", account.get("balance"), "Doo/MT5 account input was not published."),
        ("Equity", account.get("equity"), "Doo/MT5 account input was not published."),
        ("Floating P/L", account.get("floating_profit"), "No verified floating P/L input."),
        ("Used Margin", account.get("used_margin"), "No verified margin input."),
        ("Free Margin", account.get("free_margin"), "No verified free-margin input."),
        ("Margin Level", account.get("margin_level"), "No verified margin-level input."),
        ("Current Drawdown %", dd.get("current_drawdown_pct"), "Equity history is insufficient."),
        ("Maximum Drawdown %", dd.get("maximum_drawdown_pct"), "Equity history is insufficient."),
        ("Open Positions", exposure.get("open_position_count"), "No verified positions input."),
        ("BUY Exposure", exposure.get("buy_exposure"), "No verified positions input."),
        ("SELL Exposure", exposure.get("sell_exposure"), "No verified positions input."),
        ("Net Exposure", exposure.get("net_exposure"), "No verified positions input."),
        ("Planned Daily Risk", risk.get("planned_total_risk"), "Balance/risk plan is unavailable."),
        ("Remaining Daily Risk", risk.get("remaining_daily_risk"), "Balance/risk plan is unavailable."),
        ("Expected Shortfall 95%", es95.get("value"), "Minimum 30 settled returns required."),
        ("Expected Shortfall 99%", es99.get("value"), "Minimum 30 settled returns required."),
        ("1-ATR Stress Loss", stress.get("stress_1atr"), "ATR or position evidence unavailable."),
        ("2-ATR Stress Loss", stress.get("stress_2atr"), "ATR or position evidence unavailable."),
        ("3-ATR Stress Loss", stress.get("stress_3atr"), "ATR or position evidence unavailable."),
        ("Data Freshness", clock.get("watermark_status"), "Canonical completed-H1 watermark unavailable."),
        ("Connector Health", "AVAILABLE" if execution.get("status") == "AVAILABLE" else None, "No execution/API history was published."),
        ("Broker Clock Source", clock.get("broker_clock_resolution"), "Configure validated bridge, IANA timezone or manual offset."),
        ("Cross-Table Sync", _m(v8.get("field1_sync")).get("status"), "Canonical identity checks did not pass."),
        ("Morning Readiness", readiness.get("visible_status"), "V8 readiness has not been published."),
    ])
    st.caption("Expected Shortfall, Kelly and survival outputs are historical/advisory evidence only. They do not guarantee accuracy, profit or account survival.")


def _render_analysis(v8: Mapping[str, Any]) -> None:
    morning = _m(v8.get("morning")); ewma = _m(morning.get("ewma_volatility")); kelly = _m(morning.get("kelly_shadow")); ruin = _m(morning.get("risk_of_ruin_proxy")); ensemble = _m(v8.get("bates_granger")); fixed = _m(v8.get("fixed_share"))
    _metric_grid([
        ("EWMA Vol 1H", _m(ewma.get("1h")).get("value"), "Insufficient completed returns."),
        ("EWMA Vol 6H", _m(ewma.get("6h")).get("value"), "Insufficient completed returns."),
        ("EWMA Vol 24H", _m(ewma.get("24h")).get("value"), "Insufficient completed returns."),
        ("Kelly Shadow", kelly.get("fractional_kelly"), "Minimum settled sample requirement not met."),
        ("Risk-of-Ruin Proxy %", ruin.get("proxy_pct"), "Empirical proxy unavailable."),
        ("Effective Experts", ensemble.get("effective_expert_count"), "Settled model-error matrix unavailable."),
        ("Fixed-Share Turnover", fixed.get("weight_turnover"), "Settled expert losses unavailable."),
        ("Expert Switches", fixed.get("expert_switches"), "Settled expert losses unavailable."),
    ])
    st.caption("Kelly is capped shadow evidence only and never changes position size. The risk-of-ruin value is an empirical proxy, not a bankruptcy probability.")
    with st.expander("Open protected Doo Prime account, risk calculator and emergency-exit workspace", expanded=False):
        st.caption("This legacy protected workspace is imported only inside Morning → Analysis. Opening Morning Overview, History or Health does not import it.")
        try:
            from tabs.upgraded_doo_prime_home import doo_prime_panel
            doo_prime_panel()
        except Exception as exc:
            st.warning(f"Protected Doo Prime workspace is unavailable: {exc}")


def _render_history(v8: Mapping[str, Any]) -> None:
    clock = _m(v8.get("broker_time_contract"))
    st.caption(f"Broker-time label: {clock.get('shared_broker_time_display') or 'BROKER TIME UNAVAILABLE — CONFIGURE SETTINGS'}")
    st.info("Each bounded table is queried only after its own Load switch is enabled.")
    for label, table in HISTORY_TABLES.items():
        with st.expander(f"Open / Close — {label}", expanded=False):
            load = st.toggle(f"Load {label}", value=False, key=f"v8_load_{table}")
            if not load:
                st.caption("Not loaded. No database query was executed.")
                continue
            search = st.text_input("Search", key=f"v8_search_{table}", placeholder="Search visible history")
            limit = st.select_slider("Row limit", options=[25, 50, 100, 200, 500], value=100, key=f"v8_limit_{table}")
            try:
                identity = _m(v8.get("identity"))
                frame = _cached_history(
                    table, search, int(limit), str(identity.get("calculation_id") or ""),
                    str(identity.get("generation_id") or ""), str(v8.get("version") or "v8"),
                )
                quality_columns = [c for c in ("data_quality_status", "risk_status", "field1_sync_status", "cross_table_sync_status", "status", "visible_status") if c in frame.columns]
                quality_label = "UNAVAILABLE" if frame.empty or not quality_columns else " / ".join(str(frame[c].iloc[0]) for c in quality_columns[:2])
                st.caption(f"Data-quality indicator: {quality_label} · Broker-time contract: {clock.get('contract_version') or 'UNAVAILABLE'}")
                st.metric("Rows", len(frame))
                if frame.empty:
                    st.info("No rows have been published for this history yet.")
                else:
                    st.dataframe(frame, use_container_width=True, hide_index=True, height=min(520, 90 + 28 * len(frame)))
                    st.download_button("Export CSV", frame.to_csv(index=False).encode("utf-8"), file_name=f"{table}.csv", mime="text/csv", key=f"v8_export_{table}", use_container_width=True)
            except Exception as exc:
                st.warning(f"History query failed safely: {exc}")


def _render_health(v8: Mapping[str, Any]) -> None:
    readiness = _m(v8.get("readiness")); status = readiness.get("visible_status", "BLOCKED")
    if status == "READY": st.success("Morning Readiness: READY")
    elif status == "CAUTION": st.warning("Morning Readiness: CAUTION")
    else: st.error("Morning Readiness: BLOCKED")
    checks = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []
    if checks: st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
    else: st.info("Run Settings → Run Calculation + Open Lunch to publish V8 readiness evidence.")
    calibration = _m(v8.get("conformal_calibration")); governance = _m(v8.get("governance")); promotion = _m(governance.get("promotion"))
    _metric_grid([
        ("Calibration", calibration.get("status"), "No settled calibration evidence."),
        ("Drift Events", len(v8.get("drift_events") or []), "No drift state published."),
        ("Promotion", promotion.get("status"), "Research promotion evidence unavailable."),
        ("Production Influence", "ENABLED" if v8.get("production_influence_enabled") else "FALSE", "V8 defaults to shadow-only."),
    ])
    with st.expander("Calibration metadata", expanded=False):
        rows = calibration.get("metadata") if isinstance(calibration.get("metadata"), list) else []
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True) if rows else st.info("INSUFFICIENT EVIDENCE")
    with st.expander("Research promotion gates", expanded=False):
        gates = promotion.get("gates") if isinstance(promotion.get("gates"), Mapping) else {}
        st.dataframe(pd.DataFrame([{"Gate": k, "Passed": bool(v)} for k, v in gates.items()]), use_container_width=True, hide_index=True) if gates else st.info("No promotion evaluation published.")


def show(runtime_context: Mapping[str, Any] | None = None) -> None:
    st.markdown("### 🌅 Morning — Quant Control")
    # 2026-06-24 compact professional pre-trade console; read-only and shadow-only.
    try:
        from core.morning_quant_intelligence_20260624 import render_morning_quant_intelligence
        render_morning_quant_intelligence(st.session_state)
    except Exception as exc:
        st.caption(f"Morning Quant Intelligence skipped safely: {exc}")
    canonical = _canonical(); v8 = _m(canonical.get("quant_research_v8"))
    if not v8:
        st.warning("V8 Morning evidence is not published yet. Use Settings → Run Calculation + Open Lunch. Opening Morning never calculates.")
    options = ["Overview", "Analysis", "History", "Health / Readiness"]
    selected = st.selectbox("Morning workspace", options, index=options.index(st.session_state.get("morning_v8_inner", "Overview")) if st.session_state.get("morning_v8_inner", "Overview") in options else 0, key="morning_v8_inner")
    if selected == "Overview": _render_overview(v8)
    elif selected == "Analysis": _render_analysis(v8)
    elif selected == "History": _render_history(v8)
    else: _render_health(v8)


__all__ = ["show", "HISTORY_TABLES"]
