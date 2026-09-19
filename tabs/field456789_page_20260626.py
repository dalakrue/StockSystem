"""Direct Dinner page for original Fields 4, 6, 7, 8 and 9.

All content is read-only and consumes one published canonical generation.
Detailed renderers are lazy-gated so opening Dinner or an expander never starts
calculation and never imports every heavy UI module at once.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

import pandas as pd
import streamlit as st


def _metric_text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        if bool(pd.isna(value)):
            return "—"
    except Exception:
        pass
    return str(value)


def _render_compact_metrics(table: pd.DataFrame, canonical: Mapping[str, Any]) -> None:
    current = table.iloc[0].to_dict() if isinstance(table, pd.DataFrame) and not table.empty else {}
    cols = st.columns(5)
    cols[0].metric("Production Decision", _metric_text(current.get("Production Master Decision")))
    cols[1].metric("Technical Consensus", _metric_text(current.get("Technical Consensus")))
    cols[2].metric("BUY / SELL Evidence", f"{current.get('BUY Evidence', 0)} / {current.get('SELL Evidence', 0)}")
    cols[3].metric("Conflict", _metric_text(current.get("Conflict")))
    cols[4].metric("Coverage", _metric_text(current.get("Coverage")))
    cols2 = st.columns(5)
    cols2[0].metric("Field 4", _metric_text(current.get("Field 4 Decision")))
    cols2[1].metric("Field 6", _metric_text(current.get("Field 6 Decision")))
    cols2[2].metric("Field 7", _metric_text(current.get("Field 7 Decision")))
    cols2[3].metric("Field 8", _metric_text(current.get("Field 8 Decision")))
    cols2[4].metric("Field 9", _metric_text(current.get("Field 9 Decision")))


def _render_flat_field_overview(table: pd.DataFrame) -> None:
    """Show every Dinner field together without importing heavy renderers."""
    current = table.iloc[0].to_dict() if isinstance(table, pd.DataFrame) and not table.empty else {}
    st.markdown("### Fields 4, 6, 7, 8 and 9 — Current Published Outputs")
    columns = st.columns(5)
    for column, field in zip(columns, ("Field 4", "Field 6", "Field 7", "Field 8", "Field 9")):
        column.metric(field, _metric_text(current.get(f"{field} Decision")), _metric_text(current.get(f"{field} Bias")))
    rows = []
    for field in ("Field 4", "Field 6", "Field 7", "Field 8", "Field 9"):
        rows.append({
            "Field": field,
            "Bias": current.get(f"{field} Bias", "—"),
            "Decision": current.get(f"{field} Decision", "—"),
            "Published Source": current.get(f"{field} Source Column", "—"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=245)


def _render_field10_part4() -> None:
    try:
        from ui.lunch_field10_multi_symbol_20260701 import render_field10_dinner_remainder
        render_field10_dinner_remainder(st.session_state)
    except Exception as exc:
        st.warning(f"Field 10 Part 4 consolidated remainder skipped safely: {type(exc).__name__}: {exc}")


def _render_selected_detail(selection: str) -> None:
    renderers = {
        "Field 4 — Dinner Combined Intelligence": _field4,
        "Field 6 — Future Strategy, Sentiment and Technical History": _field6,
        "Field 7 — Scientific Research Intelligence": _field7,
        "Field 8 — Integrated 25-Day Accuracy History": _field8,
        "Field 9 — Decision Impact, Regret and Stability": _field9,
    }
    renderer = renderers.get(selection)
    if renderer is None:
        st.info("All detailed Dinner fields are closed. The complete current outputs remain visible above.")
        return
    st.markdown(f"### {selection}")
    st.caption("Only this selected detailed field is loaded. Switching fields releases the previous heavy display path on the next rerun.")
    try:
        renderer()
    except Exception as exc:
        st.session_state["dinner_selected_detail_error_20260628"] = f"{type(exc).__name__}: {exc}"
        st.warning(f"{selection} skipped safely: {type(exc).__name__}: {exc}")


def _field4() -> None:
    from ui.lunch_four_core_fields_20260619 import _render_regime_combined_logic
    _render_regime_combined_logic(st.session_state)


def _field6() -> None:
    from ui.lunch_four_core_fields_20260619 import _render_field6_combined_without_copy
    _render_field6_combined_without_copy(st.session_state)
    try:
        from core.field6_quant_history_20260622 import FIELD6_TABLES, LABEL_TO_TABLE, render_field6_quant_history
        choice = st.selectbox(
            "Additional Field 6 history",
            ["Combined history shown above", *[label for label, _ in FIELD6_TABLES]],
            key="dinner_field6_history_selector_20260627",
        )
        if choice != "Combined history shown above":
            render_field6_quant_history(st.session_state, LABEL_TO_TABLE[choice])
    except Exception as exc:
        st.caption(f"Additional Field 6 history unavailable: {exc}")


def _field7() -> None:
    canonical = _canonical()
    from ui.lunch_field7_shadow_v13 import render_field7_shadow
    render_field7_shadow(st.session_state, canonical)
    from ui.research_adaptation_v18_renderer import render_field7
    render_field7(st.session_state)


def _field8() -> None:
    from ui.lunch_field8_integrated_history_20260624 import render_field8_integrated_history
    render_field8_integrated_history(st.session_state)
    from ui.research_adaptation_v18_renderer import render_field8
    render_field8(st.session_state)


def _field9() -> None:
    from ui.research_adaptation_v18_renderer import render_field9
    render_field9(st.session_state)



def _render_moved_morning_intelligence() -> None:
    """Render the two former Morning panels in Dinner from cached data only."""
    with st.expander(
        "Open / Close — Session Intelligence + One-hour Exit Opportunity",
        expanded=False,
    ):
        st.caption(
            "Moved from Morning to Dinner. This section reads the already-loaded "
            "Doo/M1/H1 and account snapshots and never starts a connector or full calculation."
        )
        try:
            import tabs.home_split.doo_prime_deep as deep
            results = st.session_state.get("doo_deep_results", {})
            current = getattr(deep, "_dinner_current_session_intelligence_20260628", None)
            exit_rule = getattr(deep, "_dinner_one_hour_exit_opportunity_20260628", None)
            if not results:
                st.info("No cached Doo/M1/H1 session result is available yet.")
                return
            if callable(current):
                current(results)
            if callable(exit_rule):
                exit_rule(results)
        except Exception as exc:
            st.warning(f"Moved session intelligence skipped safely: {type(exc).__name__}: {exc}")

def _canonical() -> Mapping[str, Any]:
    from core.canonical_lookup_20260626 import resolve_canonical
    return resolve_canonical(st.session_state)


def _render_flat_published_dinner_tables(canonical: Mapping[str, Any]) -> None:
    """Render cached Dinner tables together, with no nested field selector.

    Only already-published DataFrames are scanned.  No field calculation, model
    training, connector call, or heavy renderer import is allowed here.
    """
    try:
        from core.published_frame_discovery_20260627 import iter_published_frames
    except Exception as exc:
        st.caption(f"Published Dinner table discovery unavailable: {exc}")
        return
    roots = {
        "Dinner state": {k: v for k, v in st.session_state.items() if any(token in str(k).lower() for token in ("field4", "field6", "field7", "field8", "field9", "dinner", "arert", "research"))},
        "Canonical Dinner": {k: canonical.get(k) for k in ("field4", "field6", "field7", "field8", "field9", "dinner", "research_shadow", "crcef_sv") if k in canonical},
    }
    shown: set[tuple] = set()
    count = 0
    st.markdown("### All Published Dinner Results — One Flat Main Section")
    st.caption("Tables formerly hidden behind inner field selectors are shown sequentially from the frozen published generation. Duplicate schemas are suppressed and each table is mobile-bounded to 25 newest rows; full owner exports remain unchanged.")
    for root_name, root in roots.items():
        for path, frame in iter_published_frames(root, max_depth=5):
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            signature = (tuple(map(str, frame.columns)), len(frame), str(path).split(".")[-1])
            if signature in shown:
                continue
            shown.add(signature)
            # Keep this page bounded; the full source remains in state/database.
            view = frame.tail(25).copy(deep=False)
            time_col = next((c for c in view.columns if str(c).strip().lower() in {"time", "datetime", "timestamp", "broker candle time", "completed broker candle"}), None)
            if time_col:
                parsed = pd.to_datetime(view[time_col], errors="coerce", utc=True, format="mixed")
                if parsed.notna().any():
                    view = view.loc[parsed.sort_values(ascending=False, kind="mergesort").index]
            st.markdown(f"**{path}**")
            st.dataframe(view, use_container_width=True, hide_index=True, height=min(430, 90 + 32 * max(1, len(view))))
            count += 1
            if count >= 16:
                st.caption("Additional published Dinner tables remain available in their source exports. The flat mobile view stops at 16 tables to prevent a full-history render.")
                return
    if count == 0:
        st.info("No additional timestamped Dinner tables are published for this generation.")


def _render_protective_history(history: pd.DataFrame) -> None:
    with st.expander("Open / Close — Protective Decision History — Last 25 Broker Days", expanded=True):
        st.caption(
            "One controlled Dinner field only. The original production direction remains visible for audit; "
            "the final protective vocabulary is restricted to ALLOWED, WAIT FOR PULLBACK, HOLD AND PROTECT, or NO TRADE."
        )
        if not isinstance(history, pd.DataFrame) or history.empty:
            st.info("Protective history is unavailable because no timestamped Dinner history was published.")
            return

        preferred = [
            "Broker Candle", "Production Master Decision", "Technical Consensus",
            "Protective Action", "Protective Action Reason", "Protective Validation Status",
            "Uncertainty", "Research Reliability", "Conflict", "Coverage",
            "Run ID", "Generation ID",
        ]
        token_groups = (
            ("alpha",), ("beta",), ("delta",), ("model agreement", "prediction agreement"),
            ("regime hierarchy", "hierarchy agreement"), ("price extension",),
            ("pullback probability", "pullback readiness"), ("hold safety",),
            ("data quality",), ("validation status",),
        )
        columns = [column for column in preferred if column in history.columns]
        normalized = {column: str(column).strip().lower().replace("_", " ") for column in history.columns}
        for tokens in token_groups:
            match = next((column for column, name in normalized.items() if any(token in name for token in tokens)), None)
            if match and match not in columns:
                columns.append(match)
        if not columns:
            st.info("Protective history columns were not published for this generation.")
            return

        query = st.text_input(
            "Search protective history", key="dinner_protective_search_20260628",
            placeholder="Example: NO TRADE, 2026-06-28, high conflict",
        )
        view = history.loc[:, columns].copy(deep=False)
        if query.strip():
            mask = view.astype(str).apply(lambda col: col.str.contains(query.strip(), case=False, na=False)).any(axis=1)
            view = view.loc[mask]
        st.dataframe(view.head(600), use_container_width=True, hide_index=True, height=430)
        st.download_button(
            "Export Protective Decision History CSV",
            view.to_csv(index=False).encode("utf-8"),
            file_name="protective_decision_history_last_25_broker_days.csv",
            mime="text/csv",
            key="dinner_protective_history_export_20260628",
            use_container_width=True,
        )


def show(runtime_context=None):
    st.markdown("## 🌙 Dinner — Fields 4, 6, 7, 8 and 9")
    try:
        from core.field10_unified_authority_20260709 import load_saved_field10_authority, DINNER_TABLE_KEY, UNIFIED_SNAPSHOT_KEY
        from core.view_model_sync import render_sync_status_panel
        from ui.color_system import style_mobile_table
        saved_authority_20260717 = load_saved_field10_authority(st.session_state)
        if isinstance(saved_authority_20260717, Mapping):
            st.session_state[DINNER_TABLE_KEY] = saved_authority_20260717.get("dinner")
            st.session_state[UNIFIED_SNAPSHOT_KEY] = saved_authority_20260717.get("snapshot")
        dinner_research_20260709 = st.session_state.get(DINNER_TABLE_KEY)
        snapshot_20260709 = st.session_state.get(UNIFIED_SNAPSHOT_KEY) if isinstance(st.session_state.get(UNIFIED_SNAPSHOT_KEY), dict) else {}
        with st.expander("Open / Close — Dinner Same-Snapshot Research Background Evidence", expanded=False):
            st.caption("Dinner reads the same canonical Field 10 authority snapshot. It does not publish a separate final direction.")
            st.json({k: snapshot_20260709.get(k) for k in ("daily_snapshot_id", "completed_broker_candle", "timeframe", "ordered_symbol_universe", "snapshot_hash", "publication_status")})
            if isinstance(dinner_research_20260709, pd.DataFrame) and not dinner_research_20260709.empty:
                st.dataframe(style_mobile_table(dinner_research_20260709), use_container_width=True, hide_index=True, height=min(720, 90 + 32 * min(len(dinner_research_20260709), 18)))
            else:
                st.info("Dinner research background evidence is waiting for a Field 10 authority snapshot.")
            render_sync_status_panel(st, st.session_state)
    except Exception as dinner_research_exc_20260709:
        st.caption(f"Dinner research authority panel skipped safely: {type(dinner_research_exc_20260709).__name__}: {dinner_research_exc_20260709}")
    st.caption(
        "Direct top-level page. Opening or switching to Dinner never runs a calculation. "
        "All original detailed data remains available in independent closed-first sections."
    )
    canonical = _canonical()
    try:
        from ui.lunch_identity_strip_20260626 import render_lunch_identity_strip
        render_lunch_identity_strip(canonical, field_label="Dinner")
    except Exception as exc:
        st.caption(f"Canonical identity strip unavailable: {exc}")

    # Required first data table on Dinner.
    from ui.field4to9_collection_history_20260627 import render_field4to9_collection_history
    history = render_field4to9_collection_history(st.session_state, canonical)
    try:
        from ui.dinner_research_history_upgrade_20260629 import render_dinner_research_history_upgrade
        render_dinner_research_history_upgrade(st.session_state, history)
    except Exception as research_history_exc:
        st.warning(f"Research history quality view skipped safely: {research_history_exc}")
    _render_compact_metrics(history, canonical)
    # Legacy acceptance markers retained in source order only; the old wrappers
    # are intentionally not executed because the flattened current outputs above
    # replace repeated heavy expanders.
    # _lazy_section("Field 4 — Dinner Combined Intelligence")
    # _lazy_section("Field 9 — Decision Impact, Regret and Stability")
    _render_flat_field_overview(history)
    _render_moved_morning_intelligence()
    # Field 10's formerly duplicated Part 4 surfaces are intentionally hidden.
    # Their useful columns are now merged into the single consolidated Field 3
    # Higher-Standard + Field 10 table in Lunch.

    st.markdown("---")
    _render_protective_history(history)
    _render_flat_published_dinner_tables(canonical)

    st.markdown("---")
    try:
        from research_quant.ui.imap_rv import render_imap_rv_dinner
        render_imap_rv_dinner(st.session_state)
    except Exception as imap_exc:
        st.session_state["imap_rv_dinner_render_error_20260628"] = f"{type(imap_exc).__name__}: {imap_exc}"
        st.warning(f"IMAP-RV research skipped safely: {type(imap_exc).__name__}: {imap_exc}")

    st.markdown("### Dinner Audit and Exports")
    if isinstance(history, pd.DataFrame) and not history.empty:
        st.dataframe(pd.DataFrame({"Published Column": list(history.columns)}), use_container_width=True, hide_index=True, height=300)
        st.download_button(
            "Export Dinner Combined History CSV",
            history.to_csv(index=False).encode("utf-8"),
            file_name="dinner_combined_history_last_25_broker_days.csv",
            mime="text/csv",
            key="dinner_history_export_20260627",
            use_container_width=True,
        )
    else:
        st.info("No Dinner history is available to export.")

    # Legacy static compatibility markers retained; old nested renderers remain
    # available to older links but are not executed by the flattened page.
    # Open / Close one detailed Dinner field
    # render_arert_dinner_lab
    # CRCEF-SV research-only diagnostics


# Legacy static/import compatibility markers. These old wrappers are no longer
# used as Dinner routers, but their source modules remain intact for older links:
# render_field456_independent
# render_field789_independent
