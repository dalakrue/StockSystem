"""Lazy Dinner renderer over the single published canonical generation.

Protected calculations remain in the Settings pipeline. Dinner renders only the
compact summary by default; historical tables/charts/diagnostics import the
legacy renderers only after an explicit user gate is enabled.
"""
from __future__ import annotations

from typing import Any, Dict
import time
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

from core.generation_identity_20260707 import numeric_generation

from core.compact_canonical_20260619 import get_compact_summary
from core.performance_store_20260619 import record_timing
from ui.composite_summary_cards_20260619 import render_eight_cards

UNIQUE = "dinner_unified_20260617_lazy_20260619"


def _gate(label: str, key: str, help_text: str = "") -> bool:
    return bool(st.toggle(label, value=False, key=key, help=help_text or None))


def _summary() -> Dict[str, Any]:
    return get_compact_summary(st.session_state)


def _render_all_metrics(lifecycle_renderer=None) -> Dict[str, Any]:
    """Compatibility name; now renders eight HTML cards and zero st.metric."""
    del lifecycle_renderer
    summary = _summary()
    render_eight_cards(summary, location="dinner")
    return {"summary": summary, "calculation_id": summary.get("calculation_id")}


def _legacy():
    name = "tabs._dinner_unified_center_20260617_legacy_runtime"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).with_name("dinner_unified_center_20260617_legacy.src")
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def _render_powerbi_regime_chart(ns: dict) -> None:
    _legacy()._render_powerbi_regime_chart(ns)


def _render_all_tables(context: Dict[str, Any]) -> None:
    _legacy()._render_all_tables(context)


def _render_audit_copy(context: Dict[str, Any]) -> None:
    _legacy()._render_audit_copy(context)


def _render_arcef_synthesis() -> None:
    import pandas as pd
    result = st.session_state.get("arcef_sv_result") or {}
    st.markdown("### Dinner Quantitative Master Synthesis")
    if not result:
        st.info("Run Settings → Run Calculation + Open Lunch once to publish ARCEF-SV.")
        return
    keys = ("master_decision", "direction_score", "master_strength", "reliability", "uncertainty", "entry_quality", "regime_entropy", "changepoint_probability", "valid_model_count", "excluded_model_count", "effective_independent_model_count", "expected_value", "data_quality_status", "algorithm_version")
    cols = st.columns(2)
    for i, key in enumerate(keys):
        value = result.get(key)
        cols[i % 2].metric(key.replace("_", " ").title(), "—" if value is None else value)
    st.caption(f"Canonical identity: run_id={result.get('run_id','—')} · generation_id={result.get('generation_id','—')} · broker candle={result.get('completed_broker_candle','—')}")
    interval = result.get("prediction_interval") or {}
    st.write({"lower_prediction_bound": interval.get("lower"), "central_prediction": interval.get("central"), "upper_prediction_bound": interval.get("upper"), "regime_probabilities": result.get("state_probabilities")})
    st.markdown("#### Model Contribution Ledger")
    st.dataframe(pd.DataFrame(result.get("model_contribution_ledger") or []), use_container_width=True, hide_index=True)
    st.markdown("#### ARCEF-SV History — newest first, last 25 broker days")
    st.dataframe(pd.DataFrame(result.get("history_25d") or []), use_container_width=True, hide_index=True)

def render_dinner_unified_center(ns: dict, prev_data=None, lifecycle_renderer=None) -> None:
    started = time.perf_counter()
    _render_arcef_synthesis()
    summary = _summary()
    try:
        ranking = st.session_state.get("field10_institutional_ranking_20260708")
        field3 = st.session_state.get("field3_multisymbol_regime_20260708")
        field11 = st.session_state.get("field11_similar_path_multisymbol_20260708")
        research = st.session_state.get("research_model_validation_20260708")
        if isinstance(ranking, pd.DataFrame) and not ranking.empty:
            from core.canonical_symbol_selection_20260709 import render_selector, filter_frame_for_symbol, active_symbol
            selected_symbol, _, _ = render_selector(st, st.session_state, surface="dinner", title="Dinner Multi-Symbol Selector — Load Thesis Evidence")
            selected_symbol = selected_symbol or active_symbol(st.session_state, surface="dinner")
            selected_rank = filter_frame_for_symbol(ranking, selected_symbol)
            with st.expander("🏛️ Open / Close — Dinner Master / PhD Thesis Multi-Symbol Ranking System", expanded=True):
                st.caption("Same saved evidence store as Super Quick Run: Field 10 ranking, Field 3 regime, Field 1/2 summaries, Field 11 similar path, news/NLP, and research scores.")
                tradeable = ranking[ranking.get("Entry permission", pd.Series(dtype=object)).astype(str).eq("TRADE CANDIDATE")] if "Entry permission" in ranking.columns else pd.DataFrame()
                best = tradeable.iloc[0] if not tradeable.empty else ranking.iloc[0]
                decision = "BEST TRADE CANDIDATE" if not tradeable.empty else "BEST WATCH SYMBOL — no clean trade candidate"
                top = st.columns(4)
                top[0].metric("Best symbol now", str(best.get("Symbol", "—")))
                top[1].metric("Decision", decision)
                top[2].metric("Less-risky bias", str(best.get("Less-Risky Bias", "—")))
                top[3].metric("Utility", str(best.get("InstitutionalUtility", "—")))
                st.markdown("##### Selected symbol thesis evidence")
                cols_selected = [c for c in ["Rank", "Symbol", "Timeframe", "Less-Risky Bias", "Entry permission", "InstitutionalUtility", "WeightedNetEV", "RiskPenalty", "Rank confidence", "Rank stability", "Transition Risk 6H", "Expected Return 12H", "Latest News Title", "News Sentiment", "SHAP-style explanation"] if c in ranking.columns]
                st.dataframe((selected_rank[cols_selected] if cols_selected and not selected_rank.empty else selected_rank), use_container_width=True, hide_index=True)
                st.markdown("##### Why top 4 symbols are top 4")
                cols = [c for c in ["Rank", "Symbol", "Less-Risky Bias", "Entry permission", "InstitutionalUtility", "WeightedNetEV", "RiskPenalty", "Rank confidence", "Rank stability", "Latest News Title", "SHAP-style explanation"] if c in ranking.columns]
                st.dataframe(ranking.head(4)[cols] if cols else ranking.head(4), use_container_width=True, hide_index=True)
                if isinstance(field3, pd.DataFrame) and not field3.empty:
                    st.markdown("##### Field 3 regime summary for selected symbol")
                    st.dataframe(filter_frame_for_symbol(field3, selected_symbol).head(24), use_container_width=True, hide_index=True)
                if isinstance(field11, pd.DataFrame) and not field11.empty:
                    st.markdown("##### Field 11 similar-path summary for selected symbol")
                    st.dataframe(filter_frame_for_symbol(field11, selected_symbol).head(24), use_container_width=True, hide_index=True)
                if isinstance(research, pd.DataFrame) and not research.empty:
                    st.markdown("##### Research score summary for selected symbol")
                    st.dataframe(filter_frame_for_symbol(research, selected_symbol).head(30), use_container_width=True, hide_index=True)
    except Exception as institutional_dinner_exc_20260708:
        st.caption(f"Dinner institutional snapshot unavailable: {type(institutional_dinner_exc_20260708).__name__}")
    if bool(st.session_state.get("hide_legacy_dinner_single_symbol_center_20260709", True)):
        st.caption(f"Dinner rendered in {(time.perf_counter()-started)*1000:.0f} ms from canonical multi-symbol evidence.")
        return
    st.markdown("#### Synchronized EURUSD H1 Decision Center")
    render_eight_cards(summary, location="dinner")
    if summary:
        st.caption(f"Canonical calculation ID: {summary.get('calculation_id', '-')} — identical to Lunch.")

    # True gates: code inside does not import or execute while closed.
    if _gate("Open / Close — Regime lifecycle details", "dinner_gate_lifecycle_20260619"):
        if callable(lifecycle_renderer):
            lifecycle_renderer()
    if _gate("Open / Close — PowerBI red / yellow / blue projection", "dinner_gate_chart_20260619"):
        _render_powerbi_regime_chart(ns)
    if _gate("Open / Close — KNN, Greedy, history and validation tables", "dinner_gate_tables_20260619"):
        from core.canonical_runtime_20260617 import shared_from_runtime, get_canonical
        context = {"shared": shared_from_runtime(st.session_state), "canonical": get_canonical(st.session_state)}
        _render_all_tables(context)
    if _gate("Open / Close — synchronized audit and copy", "dinner_gate_audit_20260619"):
        _render_audit_copy({"summary": summary})
    if _gate(
        "6. Regime Transition, Drift & System Trust Center",
        "dinner_gate_regime_trust_20260621",
        "Cached evidence around the existing regime. It never replaces the protected regime engine.",
    ):
        try:
            from ui.regime_transition_trust_center_20260621 import render_regime_transition_trust_center
            render_regime_transition_trust_center(state=st.session_state)
        except Exception as exc:
            st.warning("The optional Regime Trust Center could not render. The last valid core trading result remains available.")
            st.session_state["dinner_regime_trust_render_error_20260621"] = f"{type(exc).__name__}: {exc}"
            try:
                from core.regime_trust_store_20260621 import record_component_error
                canonical = st.session_state.get("canonical_decision_result") or {}
                record_component_error(
                    component="Dinner Regime Trust Center",
                    run_id=str(canonical.get("run_id") or ""),
                    calculation_generation=numeric_generation(canonical.get("calculation_generation") or canonical.get("generation_id"), default=1),
                    exception=exc, fallback_used=True,
                )
            except Exception:
                pass
    record_timing(st.session_state, "dinner_open", time.perf_counter() - started, calculation_id=summary.get("calculation_id"))


def render_dinner_regime_summary(ns: dict, prev_data=None, lifecycle_renderer=None) -> None:
    render_dinner_unified_center(ns, prev_data, lifecycle_renderer)


def render_dinner_combined_logic(ns: dict, prev_data=None, lifecycle_renderer=None) -> None:
    render_dinner_unified_center(ns, prev_data, lifecycle_renderer)


__all__ = [
    "render_dinner_unified_center", "render_dinner_regime_summary",
    "render_dinner_combined_logic", "_render_all_metrics",
]
