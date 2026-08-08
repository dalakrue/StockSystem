"""Field 3 UI for the global multi-symbol three-regime ranking."""
from __future__ import annotations
from collections.abc import Mapping, MutableMapping
from typing import Any
import json
import pandas as pd

from core.global_symbol_context import get_global_symbol_context
from ui.field3_mobile_cards_20260722 import is_phone_mode, render_responsive_records

MAIN_COLUMNS = [
    "Rank", "Symbol", "Lower Regime", "Lower Bias", "Lower Probability", "Lower Reliability",
    "Middle Regime", "Middle Bias", "Middle Probability", "Middle Reliability",
    "Higher Regime", "Higher Bias", "Higher Probability", "Higher Reliability",
    "Three-Regime Agreement", "Changepoint Risk", "Transition Risk", "DCC Correlation Penalty",
    "HRP Cluster", "Spillover TO", "Spillover FROM", "Net Spillover", "Composite Bias",
    "Composite Score", "Decision Strength", "Calibrated Reliability", "Entry Permission",
    "Block Reason", "Candle After Regime Start", "Regime Start Standard",
    "Regime Start Age Rank", "Recent Regime Change Rank", "Completed Candle",
]


def _payload_rows(evidence: pd.DataFrame, symbol: str) -> list[dict[str, Any]]:
    if not isinstance(evidence, pd.DataFrame) or evidence.empty:
        return []
    scoped = evidence.loc[evidence["Symbol"].astype(str).eq(symbol)] if "Symbol" in evidence.columns else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, row in scoped.iterrows():
        try:
            payload = json.loads(str(row.get("Payload JSON") or "{}"))
        except Exception:
            payload = {}
        payload["standard"] = row.get("Standard")
        rows.append(payload)
    return rows


def render_field3_three_regime_panel(st: Any, state: MutableMapping[str, Any]) -> None:
    context = get_global_symbol_context(state)
    ranking = state.get("field3_multisymbol_regime_20260708")
    evidence = state.get("field3_regime_evidence_v2")
    validation = state.get("field3_research_validation_v2")
    try:
        from core.regime_age_columns_20260722 import enrich_evidence, enrich_ranking
        evidence = enrich_evidence(evidence)
        ranking = enrich_ranking(ranking, evidence)
        state["field3_regime_evidence_v2"] = evidence
        state["field3_multisymbol_regime_20260708"] = ranking
    except Exception as age_exc:
        state["field3_regime_age_enrichment_error_20260722"] = f"{type(age_exc).__name__}: {age_exc}"
    st.markdown("### Field 3 — Multi-Symbol Three-Regime Ranking")
    st.caption(
        f"Global Symbol: {context.active_display_symbol or '—'} · Global Timeframe: {context.timeframe or '—'} · "
        f"Run ID: {context.parent_run_id or '—'} · Generation: {context.generation} · "
        f"Snapshot Hash: {context.snapshot_hash or '—'} · Completed Candle: {context.latest_completed_candle or '—'}"
    )
    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        st.info("No completed Field 3 generation is available. Configure and load symbols in Settings, then run a calculation.")
        return
    view = ranking[[c for c in MAIN_COLUMNS if c in ranking.columns]].copy()
    active = context.active_display_symbol
    if is_phone_mode(state):
        render_responsive_records(
            st, state, view,
            preferred_columns=[
                "Rank", "Symbol", "Higher Regime", "Higher Bias",
                "Candle After Regime Start", "Composite Bias", "Composite Score",
                "Decision Strength", "Calibrated Reliability", "Entry Permission",
                "Block Reason",
            ],
            rank_column="Rank",
            desktop_height=min(760, 90 + 38 * len(view)),
            full_table_label="Full Field 3 ranking table",
        )
    else:
        try:
            def highlight(row: pd.Series) -> list[str]:
                return ["font-weight: 800; outline: 2px solid currentColor" if str(row.get("Symbol")) == active else "" for _ in row]
            st.dataframe(view.style.apply(highlight, axis=1), use_container_width=True, hide_index=True, height=min(760, 90 + 38 * len(view)))
        except Exception:
            st.dataframe(view, use_container_width=True, hide_index=True, height=min(760, 90 + 38 * len(view)))
    from core.global_symbol_exports import build_export_bundle
    export_bundle = build_export_bundle(ranking, context)
    state["global_symbol_export_frame_v2"] = export_bundle["frame"]
    state["global_symbol_export_csv_v2"] = export_bundle["csv"]
    state["global_symbol_export_excel_v2"] = export_bundle["excel"]
    state["global_symbol_export_copy_v2"] = export_bundle["copy"]
    state["global_symbol_export_api_v2"] = export_bundle["api"]
    state["global_symbol_export_powerbi_v2"] = export_bundle["powerbi"]
    export_cols = st.columns(2)
    export_cols[0].download_button(
        "Download Full Field 3 Ranking CSV", data=export_bundle["csv"],
        file_name=f"field3_three_regime_{context.snapshot_hash or 'current'}.csv", mime="text/csv",
        use_container_width=True, key="field3_v2_download_full_csv",
    )
    export_cols[1].download_button(
        "Download Full Field 3 Ranking Excel", data=export_bundle["excel"],
        file_name=f"field3_three_regime_{context.snapshot_hash or 'current'}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True, key="field3_v2_download_full_excel",
    )
    detail = ranking.loc[ranking["Symbol"].astype(str).eq(active)] if active and "Symbol" in ranking.columns else pd.DataFrame()
    if detail.empty:
        st.warning("The globally selected symbol has no row in this completed Field 3 generation.")
        return
    st.markdown(f"#### Active Symbol Detail — {active}")
    if is_phone_mode(state):
        render_responsive_records(
            st, state, detail,
            preferred_columns=[
                "Rank", "Symbol", "Lower Regime", "Lower Bias", "Middle Regime", "Middle Bias",
                "Higher Regime", "Higher Bias", "Candle After Regime Start", "Regime Start Standard",
                "Composite Bias", "Composite Score", "Decision Strength", "Calibrated Reliability",
                "Entry Permission", "Block Reason", "Completed Candle",
            ],
            rank_column="Rank",
            desktop_height=360,
            full_table_label="Full active-symbol detail",
            max_phone_rows=1,
        )
    else:
        st.dataframe(detail, use_container_width=True, hide_index=True)
    payloads = _payload_rows(evidence, active)
    detail_specs = [
        ("posterior_probabilities", "Posterior Probabilities"),
        ("transition_matrix", "Transition Matrix"),
        ("expected_regime_duration", "Expected Regime Duration"),
        ("change_probability_history", "Change History"),
        ("feature_evidence", "Feature Evidence"),
        ("validation", "Model Validation"),
    ]
    for key, title in detail_specs:
        with st.expander(title, expanded=False):
            content = [{"standard": p.get("standard"), key: p.get(key)} for p in payloads]
            st.json(content)
    with st.expander("Rank Explanation", expanded=False):
        try:
            st.json(json.loads(str(detail.iloc[0].get("Rank Explanation") or "{}")))
        except Exception:
            st.write(detail.iloc[0].get("Rank Explanation"))
    with st.expander("Correlation Cluster", expanded=False):
        st.json({
            "symbol": active, "hrp_cluster": detail.iloc[0].get("HRP Cluster"),
            "dcc_penalty": detail.iloc[0].get("DCC Correlation Penalty"),
        })
    with st.expander("Spillover Network", expanded=False):
        st.json({
            "symbol": active, "to": detail.iloc[0].get("Spillover TO"),
            "from": detail.iloc[0].get("Spillover FROM"), "net": detail.iloc[0].get("Net Spillover"),
        })
    with st.expander("Data Lineage", expanded=False):
        st.json({
            "universe_id": context.universe_id, "parent_run_id": context.parent_run_id,
            "generation": context.generation, "timeframe": context.timeframe,
            "snapshot_hash": context.snapshot_hash, "completed_candle": context.latest_completed_candle,
            "source_data_hash": detail.iloc[0].get("Source Data Hash"),
            "evidence_hash": detail.iloc[0].get("Evidence Hash"),
        })
    if isinstance(validation, pd.DataFrame) and not validation.empty:
        with st.expander("Research Validation — Exact Saved Evidence", expanded=False):
            scoped = validation.loc[validation["Symbol"].astype(str).eq(active)] if "Symbol" in validation.columns else validation
            try:
                from core.regime_age_columns_20260722 import add_age_alias_to_table
                scoped = add_age_alias_to_table(scoped, fallback_age=detail.iloc[0].get("Candle After Regime Start"))
            except Exception:
                pass
            st.dataframe(scoped, use_container_width=True, hide_index=True)


__all__ = ["render_field3_three_regime_panel", "MAIN_COLUMNS"]
