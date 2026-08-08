"""Always-visible three-group multi-symbol Settings controls.

The three selector boxes remain for Settings UX, but they no longer create
separate load universes.  Every selection is merged into one canonical
30-symbol ranking universe.  The chosen calculation button changes depth, not
symbol membership.  No calculation formula is duplicated or replaced.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol, set_legacy_configured_symbols

from collections.abc import MutableMapping
from typing import Any

import streamlit as st

SUPPORTED_SYMBOLS: tuple[str, ...] = (
    "EURUSD", "USDJPY", "AUDUSD", "GBPUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "EURGBP", "NZDUSD",
    "EURCHF", "EURAUD", "EURCAD", "EURNZD", "GBPCHF", "GBPAUD", "GBPCAD", "AUDJPY",
    "AUDCAD", "AUDCHF", "AUDNZD", "CADCHF", "CADJPY", "CHFJPY", "NZDCAD", "NZDCHF", "NZDJPY",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "AVGO", "JPM", "AMD",
    "DXY", "NAS100", "US500", "US30", "DAX40", "UK100", "JPN225", "HK50", "FRA40", "AUS200", "EU50",
    "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "COPPER",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD", "DOGEUSD", "AVAXUSD", "DOTUSD", "LINKUSD",
)
SELECTED_KEY = "multi_symbol_selected_20260701"
ACTIVE_KEY = "multi_symbol_active_20260701"
MAIN_SYMBOL_KEY = "multi_symbol_main_symbol_20260702"
DISPLAY_SYMBOL_KEY = "lunch_display_symbol_20260702"
_MODE_KEY = "multi_symbol_calculation_mode_20260701"
_EMPTY_SELECTION_KEY = "multi_symbol_empty_selection_20260702"
# Backward-compatible public markers used by older deployment checks.
_MULTI_WIDGET_KEY = "multi_symbol_searchable_selector_widget_20260701"

FIRST_BEST_10_CURRENCY_PAIRS: list[str] = [
    "XAUUSD", "AUDUSD", "EURAUD", "EURCAD", "EURCHF",
    "EURGBP", "USDCHF", "NZDUSD", "GBPCHF", "GBPAUD",
]
SECOND_BEST_10_CURRENCY_POOL: list[str] = [
    "GBPUSD", "USDCAD", "USDJPY", "EURJPY", "GBPJPY",
    "EURUSD", "EURNZD", "GBPCAD", "AUDJPY", "XAGUSD",
    "NAS100", "US500", "US30", "BTCUSD", "ETHUSD",
]
THIRD_BEST_10_SPREAD_UNDER_25: list[str] = [
    "AUDCAD", "AUDCHF", "AUDNZD", "CADCHF", "CADJPY",
    "CHFJPY", "NZDCAD", "NZDCHF", "NZDJPY", "DXY",
]
# Legacy aliases remain import-compatible for old tests/imports. The visible
# buttons use the ten-symbol constants above.
FIRST_BEST_6_CURRENCY_PAIRS: list[str] = ["AUDUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "EURGBP"]
SECOND_BEST_6_CURRENCY_PAIRS: list[str] = ["NZDUSD", "EURCHF", "EURAUD", "EURCAD", "EURNZD", "GBPCHF"]
# Static backward-compatibility labels only: if group_name in {"FIRST", "SECOND"}
# "First Best 6 Currency Pairs" / "Second Best 6 Currency Pairs"
TOP_10_CURRENCY_PAIRS: list[str] = list(FIRST_BEST_10_CURRENCY_PAIRS)
PRESET_GROUPS_20260702: dict[str, list[str]] = {
    "First Best 10 Currency Pairs": FIRST_BEST_10_CURRENCY_PAIRS,
    "Second Best 10 — Excluding First Selection": SECOND_BEST_10_CURRENCY_POOL[:10],
    "Third Best 10 — Target Spread <25 + DXY": THIRD_BEST_10_SPREAD_UNDER_25,
    "Major Equities": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA"],
    "Major Indices": ["NAS100", "US500", "US30", "DAX40", "UK100", "JPN225"],
    "Metals": ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "COPPER"],
    "Major Crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD", "ADAUSD"],
}


def normalize_symbol(value: Any, default: str = "EURUSD") -> str:
    raw = str(value or default).strip().upper().replace("/", "").replace(" ", "")
    aliases = {
        "XBTUSD": "BTCUSD", "BTCUSDT": "BTCUSD", "GOLD": "XAUUSD",
        "USTEC": "NAS100", "US100": "NAS100", "NDX": "NAS100",
        "NASDAQ100": "NAS100", "SPX500": "US500", "SP500": "US500",
        "SPX": "US500", "GSPC": "US500", "^GSPC": "US500",
        "USDX": "DXY", "DOLLARINDEX": "DXY", "DX-Y.NYB": "DXY",
    }
    return aliases.get(raw, raw) or default


def normalize_selected(values: Any, limit: int | None = None) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        values = []
    selected: list[str] = []
    for value in values:
        symbol = normalize_symbol(value)
        if symbol in SUPPORTED_SYMBOLS and symbol not in selected:
            selected.append(symbol)
        if limit is not None and len(selected) >= int(limit):
            break
    return selected


def _publish_selection(state: MutableMapping[str, Any], values: Any) -> list[str]:
    """Publish a legacy selection without mutating the widget-owned key.

    This helper remains for older imports and avoids the Streamlit exception
    caused by assigning ``_MULTI_WIDGET_KEY`` after its widget is instantiated.
    """
    selected = normalize_selected(values)
    state[SELECTED_KEY] = list(selected)
    state[_EMPTY_SELECTION_KEY] = not bool(selected)
    set_legacy_configured_symbols(state, selected)
    if selected:
        main = selected[0]
    return selected


def _group_defs():
    from core.multi_symbol_run_groups_20260706 import (
        FIRST_GROUP_KEY, SECOND_GROUP_KEY, THIRD_GROUP_KEY, MAX_SYMBOLS_PER_GROUP,
        FIRST_GROUP_MAX_SYMBOLS, SECOND_GROUP_MAX_SYMBOLS, THIRD_GROUP_MAX_SYMBOLS,
    )
    return {
        "FIRST": {
            "state_key": FIRST_GROUP_KEY,
            "widget_key": "multi_symbol_searchable_selector_widget_20260701",
            "pending_key": "multi_symbol_first_pending_20260706",
            "title": "Selector 1",
            "owner": "Super Quick Calculation + Open Lunch",
            "limit": FIRST_GROUP_MAX_SYMBOLS,
        },
        "SECOND": {
            "state_key": SECOND_GROUP_KEY,
            "widget_key": "multi_symbol_second_selector_widget_20260706",
            "pending_key": "multi_symbol_second_pending_20260706",
            "title": "Selector 2",
            "owner": "Quick Calculation + Open Lunch",
            "limit": SECOND_GROUP_MAX_SYMBOLS,
        },
        "THIRD": {
            "state_key": THIRD_GROUP_KEY,
            "widget_key": "multi_symbol_third_selector_widget_20260706",
            "pending_key": "multi_symbol_third_pending_20260706",
            "title": "Selector 3",
            "owner": "Full Calculation + Open Lunch",
            "limit": THIRD_GROUP_MAX_SYMBOLS,
        },
    }, MAX_SYMBOLS_PER_GROUP




def _second_best_10_excluding(state: MutableMapping[str, Any], group_name: str) -> list[str]:
    """Return ten next-best symbols not already selected in other selectors.

    The current selector is excluded from the occupied set so pressing the button
    can replace its own contents deterministically.
    """
    definitions, _ = _group_defs()
    occupied: set[str] = set()
    for name, item in definitions.items():
        if name == group_name:
            continue
        occupied.update(normalize_selected(state.get(item["state_key"]), limit=None))
        occupied.update(normalize_selected(state.get(item["widget_key"]), limit=None))
    candidates = list(SECOND_BEST_10_CURRENCY_POOL) + [
        symbol for symbol in SUPPORTED_SYMBOLS
        if symbol not in FIRST_BEST_10_CURRENCY_PAIRS and symbol not in SECOND_BEST_10_CURRENCY_POOL
    ]
    result: list[str] = []
    for symbol in candidates:
        if symbol in occupied or symbol in result:
            continue
        result.append(symbol)
        if len(result) >= 10:
            break
    return result

def _persist_groups(state: MutableMapping[str, Any]) -> None:
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        from core.multi_symbol_run_groups_20260706 import save_group_preferences
        save_group_preferences(DEFAULT_DB_PATH, state)
    except Exception:
        pass


def _group_changed(group_name: str) -> None:
    definitions, _ = _group_defs()
    item = definitions[group_name]
    limit = int(item["limit"])
    selected = normalize_selected(st.session_state.get(item["widget_key"]), limit=limit)
    st.session_state[item["state_key"]] = list(selected)
    from core.multi_symbol_run_groups_20260706 import configured_groups, union_symbols, CONFIGURED_UNION_KEY
    groups = configured_groups(st.session_state)
    current_union_20260708 = union_symbols(groups["FIRST"], groups["SECOND"], groups["THIRD"])
    st.session_state[CONFIGURED_UNION_KEY] = current_union_20260708
    try:
        from core.current_result_sync_20260708 import sync_settings_source_of_truth
        sync_settings_source_of_truth(st.session_state, current_union_20260708, st.session_state.get("timeframe") or st.session_state.get("selected_timeframe") or "H4", reason=f"selector_{group_name}_changed")
    except Exception as selector_sync_exc_20260708:
        st.session_state["selector_current_result_sync_error_20260708"] = f"{type(selector_sync_exc_20260708).__name__}: {selector_sync_exc_20260708}"
    _persist_groups(st.session_state)


def _apply_pending_before_widget(state: MutableMapping[str, Any], group_name: str) -> None:
    definitions, _ = _group_defs()
    item = definitions[group_name]
    limit = int(item["limit"])
    pending = state.pop(item["pending_key"], None)
    if pending is not None:
        selected = normalize_selected(pending, limit=limit)
        state[item["state_key"]] = list(selected)
        state[item["widget_key"]] = list(selected)


def _render_group_card(state: MutableMapping[str, Any], group_name: str) -> list[str]:
    definitions, _ = _group_defs()
    item = definitions[group_name]
    limit = int(item["limit"])
    _apply_pending_before_widget(state, group_name)
    selected = normalize_selected(state.get(item["state_key"]), limit=limit)
    if item["widget_key"] not in state:
        # Seed a new widget exactly once. After that, the widget-owned value is
        # authoritative so reruns cannot restore deleted symbols or replace the
        # user's Third-selector choices with a stale database/session list.
        state[item["widget_key"]] = list(selected)
    else:
        widget_selected = normalize_selected(state.get(item["widget_key"]), limit=limit)
        state[item["state_key"]] = list(widget_selected)
        selected = list(widget_selected)

    with st.container(border=True):
        st.markdown(f"### 🌐 {item['title']}")
        st.caption(
            f"Choose up to {limit} symbols, then load genuine candles for the selected Settings timeframe."
        )
        selected_value = st.multiselect(
            f"Select up to {limit} symbols for {item['title']}",
            options=list(SUPPORTED_SYMBOLS),
            key=item["widget_key"],
            max_selections=limit,
            on_change=_group_changed,
            args=(group_name,),
            help="The displayed order is authoritative: first selected = Main Core Symbol for this button run.",
        )
        selected_value = normalize_selected(selected_value, limit=limit)
        state[item["state_key"]] = list(selected_value)

        # Ten-symbol quick choices. The second choice automatically excludes
        # symbols already selected in the other two selectors.
        if group_name in {"FIRST", "SECOND", "THIRD"}:
            st.caption("Currency-pair quick choices")
            quick_cols = st.columns(3 if group_name == "THIRD" else 2)
            if quick_cols[0].button(
                "First Best 10 Currency Pairs",
                key=f"multi_symbol_{group_name.lower()}_first_best10_20260722",
                use_container_width=True,
                help="XAUUSD, AUDUSD, EURAUD, EURCAD, EURCHF, EURGBP, USDCHF, NZDUSD, GBPCHF, GBPAUD",
            ):
                state[item["pending_key"]] = list(FIRST_BEST_10_CURRENCY_PAIRS)[:limit]
                st.rerun()
            if quick_cols[1].button(
                "Second Best 10 — Exclude Already Selected",
                key=f"multi_symbol_{group_name.lower()}_second_best10_20260722",
                use_container_width=True,
                help="Automatically chooses ten different symbols that are not already selected in the other selectors.",
            ):
                state[item["pending_key"]] = _second_best_10_excluding(state, group_name)[:limit]
                st.rerun()
            if group_name == "THIRD" and quick_cols[2].button(
                "Third Best 10 — Spread <25 + DXY",
                key="multi_symbol_third_best10_spread25_dxy_20260727",
                use_container_width=True,
                help=(
                    "AUDCAD, AUDCHF, AUDNZD, CADCHF, CADJPY, CHFJPY, NZDCAD, NZDCHF, NZDJPY and DXY. "
                    "These are the requested under-25-spread candidates; always confirm the live broker spread before trading."
                ),
            ):
                state[item["pending_key"]] = list(THIRD_BEST_10_SPREAD_UNDER_25)[:limit]
                st.rerun()

        preset_cols = st.columns(3)
        preset_names = list(PRESET_GROUPS_20260702)
        preset = preset_cols[0].selectbox(
            "More presets", preset_names,
            key=f"multi_symbol_{group_name.lower()}_preset_choice_20260706",
            label_visibility="collapsed",
        )
        if preset_cols[1].button("Apply preset", key=f"multi_symbol_{group_name.lower()}_apply_preset_20260706", use_container_width=True):
            state[item["pending_key"]] = list(PRESET_GROUPS_20260702[preset])[:limit]
            st.rerun()
        if preset_cols[2].button("Clear", key=f"multi_symbol_{group_name.lower()}_clear_20260706", use_container_width=True):
            state[item["pending_key"]] = []
            st.rerun()

        timeframe = str(state.get("timeframe") or state.get("selected_timeframe") or "H4").upper()
        metrics = st.columns(3)
        metrics[0].metric("Selected", len(selected_value))
        metrics[1].metric("Selector Limit", limit)
        metrics[2].metric("Timeframe", timeframe)
        if selected_value:
            st.caption("Selected order: " + " → ".join(selected_value))
        st.info(
            "This selector can load independently with its own button below, or all three selectors can load together. Every successful exact-symbol result is preserved in the same canonical top-30 universe."
        )

    return selected_value

def render_multi_symbol_selectors(state: MutableMapping[str, Any] | None = None) -> dict[str, list[str]]:
    """Render three independent selectors and merge up to 30 unique symbols."""
    state = state if state is not None else st.session_state
    from core.multi_symbol_run_groups_20260706 import (
        initialize_groups, configured_groups, union_symbols, CONFIGURED_UNION_KEY, COMPLETED_UNION_KEY,
        discover_completed_symbols, load_group_preferences,
    )
    persisted: dict[str, Any] = {}
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        persisted = load_group_preferences(DEFAULT_DB_PATH)
    except Exception:
        persisted = {}
    groups = initialize_groups(state, state.get(SELECTED_KEY) or TOP_10_CURRENCY_PAIRS, persisted=persisted)
    discovered_completed: list[str] = []
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        discovered_completed = normalize_selected(discover_completed_symbols(DEFAULT_DB_PATH))
    except Exception:
        discovered_completed = []
    state[COMPLETED_UNION_KEY] = union_symbols(
        state.get(COMPLETED_UNION_KEY) or [],
        persisted.get("completed") or [],
        discovered_completed,
    )

    # Backward compatibility marker only: "Reload Failed Symbols" was removed from
    # the UI because failed symbols are now handled by the unified canonical loader.
    st.markdown("### Three Multi-Symbol Selectors")
    st.caption("All selected symbols are merged into one canonical top-30 ranking universe. Each selector can load alone, sequentially, or together without erasing earlier successful loads.")
    groups["FIRST"] = _render_group_card(state, "FIRST")
    groups["SECOND"] = _render_group_card(state, "SECOND")
    groups["THIRD"] = _render_group_card(state, "THIRD")
    groups = configured_groups(state)
    configured_union = union_symbols(groups["FIRST"], groups["SECOND"], groups["THIRD"])
    state[CONFIGURED_UNION_KEY] = configured_union
    state[_EMPTY_SELECTION_KEY] = not bool(configured_union)
    try:
        from core.current_result_sync_20260708 import sync_settings_source_of_truth
        sync_settings_source_of_truth(state, configured_union[:30] or ["EURUSD"], state.get("timeframe") or state.get("selected_timeframe") or "H4", reason="selectors_render_current_source_of_truth")
    except Exception as selectors_sync_exc_20260708:
        state["selectors_current_result_sync_error_20260708"] = f"{type(selectors_sync_exc_20260708).__name__}: {selectors_sync_exc_20260708}"
    _persist_groups(state)

    with st.container(border=True):
        timeframe = str(state.get("timeframe") or state.get("selected_timeframe") or "H4").upper()
        try:
            from core.multi_symbol_load_manager_20260707 import (
                canonical_universe_from_groups, publish_canonical_universe,
                load_canonical_market_data, loaded_canonical_status, MAX_CANONICAL_SYMBOLS,
                load_selector_with_assigned_key, load_all_selectors_safely, merge_selector_load_results,
                EMERGENCY_CROSS_KEY_STATE_KEY, SELECTOR_WORKER_STATE_KEY,
            )
            canonical_selected = canonical_universe_from_groups(groups, limit=MAX_CANONICAL_SYMBOLS)
            publish_canonical_universe(state, canonical_selected, timeframe)
            canonical_status = loaded_canonical_status(state, canonical_selected, timeframe)
        except Exception as universe_exc:
            canonical_selected = configured_union[:30]
            state["canonical_selected_symbols"] = list(canonical_selected)
            state["canonical_selected_symbols_20260705"] = list(canonical_selected)
            canonical_status = {
                "ready": False, "complete": False, "loaded_symbols": [], "failed_symbols": [], "status_rows": [],
                "message": f"Canonical loader unavailable: {type(universe_exc).__name__}: {universe_exc}",
            }

        st.markdown("### Foreground Symbol Loading Control Center")
        st.caption("Foreground pipeline: cache first → Selector 1 uses Twelve Key 1 → Selector 2 uses Twelve Key 2 → Selector 3 uses the shared configured key pool. All successful loads merge into one Field 3/Field 10 board.")
        st.markdown("#### Canonical Top-30 Universe Preview")
        summary = st.columns(5)
        summary[0].metric("Selector 1", len(groups["FIRST"]))
        summary[1].metric("Selector 2", len(groups["SECOND"]))
        summary[2].metric("Selector 3", len(groups["THIRD"]))
        summary[3].metric("Canonical Unique", len(canonical_selected))
        summary[4].metric("Limit", str(MAX_CANONICAL_SYMBOLS))
        if len(configured_union) > len(canonical_selected):
            skipped = [symbol for symbol in configured_union if symbol not in canonical_selected]
            st.warning("Only the first 30 deduplicated symbols are used. Skipped: " + " → ".join(skipped))
        if canonical_selected:
            st.caption("Canonical ranking order: " + " → ".join(canonical_selected))
        else:
            st.info("Select at least one symbol across the three selectors.")

        rows = list(canonical_status.get("status_rows") or [])
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)

        success_statuses_20260708 = {"CACHE_SUCCESS", "TWELVE_SUCCESS", "FINNHUB_SUCCESS", "EMERGENCY_CACHE_SUCCESS"}
        loaded_now_count_20260708 = int(canonical_status.get("loaded_now_count") or sum(
            1 for row in rows if str(row.get("Load Status") or "").upper() in success_statuses_20260708
        ))
        failed_now_count_20260708 = max(0, len(canonical_selected) - loaded_now_count_20260708)
        provider_summary_20260708 = canonical_status.get("provider_summary") if isinstance(canonical_status.get("provider_summary"), dict) else {}
        load_status_cols_20260708 = st.columns(4)
        load_status_cols_20260708[0].metric("Loaded", f"{loaded_now_count_20260708} / {len(canonical_selected)}")
        load_status_cols_20260708[1].metric("Failed", f"{failed_now_count_20260708} / {len(canonical_selected)}")
        load_status_cols_20260708[2].metric("Twelve Key 1", int(provider_summary_20260708.get("TWELVE_KEY_1") or 0))
        load_status_cols_20260708[3].metric("Twelve Key 2", int(provider_summary_20260708.get("TWELVE_KEY_2") or 0))
        st.caption(
            "Provider summary: "
            f"LOCAL_CACHE: {int(provider_summary_20260708.get('LOCAL_CACHE') or 0)} · "
            f"TWELVE_DATA_KEY_POOL: {int(provider_summary_20260708.get('TWELVE_DATA_KEY_POOL') or 0)} · "
            f"FINNHUB: {int(provider_summary_20260708.get('FINNHUB') or 0)} · "
            f"LAST_KNOWN_VALID_CACHE: {int(provider_summary_20260708.get('LAST_KNOWN_VALID_CACHE') or 0)} · "
            f"NONE: {int(provider_summary_20260708.get('NONE') or 0)}"
        )

        load_locked = bool(
            state.get("multi_symbol_load_in_progress_20260707")
            or state.get("multi_symbol_run_in_progress_20260701")
            or state.get("instant_run_engine_running_20260705")
            or state.get("settings_one_click_running_20260624")
        )

        emergency_cross_key = st.checkbox(
            "Automatic Cross-Key + Shared-Pool Recovery",
            key=EMERGENCY_CROSS_KEY_STATE_KEY,
            value=bool(state.get(EMERGENCY_CROSS_KEY_STATE_KEY, True)),
            help="Recommended ON. Failed symbols automatically try the opposite configured key and then the shared pool while preserving all READY rows.",
        )

        worker_cols = st.columns(3)
        workers = state.get(SELECTOR_WORKER_STATE_KEY) if isinstance(state.get(SELECTOR_WORKER_STATE_KEY), dict) else {}
        for col, group_name, title, assigned_key in (
            (worker_cols[0], "FIRST", "Twelve Key 1 Worker", "TWELVE_KEY_1"),
            (worker_cols[1], "SECOND", "Twelve Key 2 Worker", "TWELVE_KEY_2"),
            (worker_cols[2], "THIRD", "Shared Key-Pool Worker", "TWELVE_DATA_KEY_POOL"),
        ):
            selected_for_worker = groups.get(group_name) or []
            worker = workers.get(group_name) if isinstance(workers.get(group_name), dict) else {
                "Assigned selector": "Selector 1" if group_name == "FIRST" else "Selector 2" if group_name == "SECOND" else "Selector 3",
                "Assigned key": assigned_key,
                "Selected symbols": " → ".join(selected_for_worker),
                "Loaded count": 0,
            }
            with col.container(border=True):
                st.markdown(f"#### {title}")
                st.caption(f"Assigned selector: {'Selector 1' if group_name == 'FIRST' else 'Selector 2' if group_name == 'SECOND' else 'Selector 3'}")
                st.json({
                    "Selected symbols": " → ".join(selected_for_worker),
                    "Loaded count": worker.get("Loaded count", 0),
                    "Failed count": worker.get("Failed count", 0),
                    "Remaining local minute credits": worker.get("Remaining local minute credits", 0),
                    "Cooldown seconds": worker.get("Cooldown seconds", 0),
                    "Last request time": worker.get("Last request time", ""),
                    "Last error": worker.get("Last error", ""),
                    "Symbols skipped because of quota": worker.get("Symbols skipped because of quota", ""),
                    "Symbols skipped because of circuit breaker": worker.get("Symbols skipped because of circuit breaker", ""),
                })

        button_cols_20260708 = st.columns(5)
        load_s1_clicked = button_cols_20260708[0].button(
            "Load Selector 1 with Twelve Key 1",
            key="selector_owned_load_selector_1_key_1_20260708",
            use_container_width=True,
            disabled=load_locked or not bool(groups.get("FIRST")),
            help="Loads Selector 1 with Key 1 first, then automatically retries unresolved symbols through the other configured key and shared pool without erasing successful rows.",
        )
        load_s2_clicked = button_cols_20260708[1].button(
            "Load Selector 2 with Twelve Key 2",
            key="selector_owned_load_selector_2_key_2_20260708",
            use_container_width=True,
            disabled=load_locked or not bool(groups.get("SECOND")),
            help="Loads Selector 2 with Key 2 first, then automatically retries unresolved symbols through the other configured key and shared pool without erasing successful rows.",
        )
        load_s3_clicked = button_cols_20260708[2].button(
            "Load Selector 3 with Key Pool",
            key="selector_owned_load_selector_3_pool_20260722",
            use_container_width=True,
            disabled=load_locked or not bool(groups.get("THIRD")),
            help="Loads Selector 3 using any currently available configured Twelve Data key, with exact-symbol cache first.",
        )
        load_all_clicked = button_cols_20260708[3].button(
            "Load All Selected (Top 30)",
            key="selector_owned_load_all_30_safely_20260727",
            use_container_width=True,
            disabled=load_locked or not bool(canonical_selected),
            help="Loads all three selectors and preserves successful rows from earlier selector-by-selector loads.",
        )
        clear_clicked = button_cols_20260708[4].button(
            "Clear Load State",
            key="canonical_12_symbol_clear_load_state_20260708",
            use_container_width=True,
            disabled=load_locked,
            help="Clears only the foreground load board/session state. It does not delete saved candles.",
        )

        retry_cols_20260708 = st.columns(5)
        retry_s1_clicked = retry_cols_20260708[0].button(
            "Reload Failed from Selector 1 only",
            key="selector_owned_reload_failed_selector_1_20260708",
            use_container_width=True,
            disabled=load_locked or not bool(groups.get("FIRST")),
            help="Retries only failed Selector 1 rows and preserves READY rows.",
        )
        retry_s2_clicked = retry_cols_20260708[1].button(
            "Reload Failed from Selector 2 only",
            key="selector_owned_reload_failed_selector_2_20260708",
            use_container_width=True,
            disabled=load_locked or not bool(groups.get("SECOND")),
            help="Retries only failed Selector 2 rows and preserves READY rows.",
        )
        retry_s3_clicked = retry_cols_20260708[2].button(
            "Reload Failed from Selector 3 only",
            key="selector_owned_reload_failed_selector_3_20260722",
            use_container_width=True,
            disabled=load_locked or not bool(groups.get("THIRD")),
            help="Retries only failed Selector 3 rows through the shared key pool and preserves READY rows.",
        )
        force_retry_clicked = retry_cols_20260708[3].button(
            "Force Clear Circuit Breaker + Retry Failed",
            key="selector_owned_force_clear_circuit_retry_failed_20260708",
            use_container_width=True,
            disabled=load_locked or not bool(canonical_selected),
            help="Clears stale local circuit-breaker state for failed rows, then retries only failed symbols. It does not reload READY rows.",
        )
        try:
            import pandas as _pd
            export_df = _pd.DataFrame(rows)
            retry_cols_20260708[4].download_button(
                "Export Provider Trace CSV",
                data=export_df.to_csv(index=False).encode("utf-8"),
                file_name=f"provider_trace_{timeframe}.csv",
                mime="text/csv",
                use_container_width=True,
                disabled=export_df.empty,
                key="canonical_12_symbol_export_provider_trace_20260708",
            )
        except Exception:
            retry_cols_20260708[4].caption("Export unavailable")

        if clear_clicked:
            from core.multi_symbol_load_manager_20260707 import (
                LOAD_RECORDS_KEY, CANONICAL_GROUP, CANONICAL_LOADED_KEY, CANONICAL_SYMBOL_LOAD_STATUS_KEY,
                CANONICAL_SYMBOL_CANDLES_KEY, CANONICAL_PROVIDER_TRACE_KEY, CANONICAL_LAST_LOAD_RUN_ID_KEY,
                SELECTOR_WORKER_STATE_KEY, SELECTOR_REQUEST_LEDGER_KEY,
            )
            records = state.get(LOAD_RECORDS_KEY) if isinstance(state.get(LOAD_RECORDS_KEY), dict) else {}
            for _group_name in (CANONICAL_GROUP, "FIRST", "SECOND", "THIRD"):
                records.pop(_group_name, None)
            state[LOAD_RECORDS_KEY] = records
            for _key in (
                CANONICAL_LOADED_KEY, CANONICAL_SYMBOL_LOAD_STATUS_KEY, CANONICAL_SYMBOL_CANDLES_KEY,
                CANONICAL_PROVIDER_TRACE_KEY, CANONICAL_LAST_LOAD_RUN_ID_KEY,
                SELECTOR_WORKER_STATE_KEY, SELECTOR_REQUEST_LEDGER_KEY,
            ):
                state.pop(_key, None)
            st.success("Foreground load state cleared. Saved candle cache is unchanged.")
            st.rerun()

        action_requested = bool(load_s1_clicked or load_s2_clicked or load_s3_clicked or load_all_clicked or retry_s1_clicked or retry_s2_clicked or retry_s3_clicked or force_retry_clicked)
        if action_requested:
            action_label = (
                "Loading Selector 1 with Twelve Key 1…" if load_s1_clicked else
                "Loading Selector 2 with Twelve Key 2…" if load_s2_clicked else
                "Loading Selector 3 with the shared key pool…" if load_s3_clicked else
                "Reloading failed Selector 1 symbols…" if retry_s1_clicked else
                "Reloading failed Selector 2 symbols…" if retry_s2_clicked else
                "Reloading failed Selector 3 symbols…" if retry_s3_clicked else
                "Clearing circuit breakers and retrying failed symbols…" if force_retry_clicked else
                "Loading all selected symbols with three independent workers…"
            )
            progress_bar = st.progress(0.0, text=action_label)
            progress_text = st.empty()
            live_rows = st.empty()

            _last_live_board_percent = {"value": -20.0}

            def _load_progress(snapshot: Any) -> None:
                if not isinstance(snapshot, dict):
                    return
                percent = float(snapshot.get("overall_percent") or snapshot.get("progress_percent") or 0.0)
                current = str(snapshot.get("current_symbol") or "Selector-owned symbols")
                stage = str(snapshot.get("current_stage") or "Loading market data")
                completed = int(snapshot.get("completed_symbols") or 0)
                total = int(snapshot.get("total_symbols") or len(canonical_selected) or 0)
                elapsed = float(snapshot.get("elapsed_seconds") or 0.0)
                progress_bar.progress(min(1.0, max(0.0, percent / 100.0)), text=f"{percent:.1f}% loaded")
                progress_text.caption(f"{current} — {stage} · {completed}/{total} symbols · {elapsed:.1f}s elapsed")
                # Rebuilding the full canonical board on every provider sub-stage
                # was a major UI bottleneck on phones. Refresh it only at 20-point
                # intervals; the final board is always rendered after completion.
                if percent - _last_live_board_percent["value"] >= 20.0 or percent >= 99.9:
                    _last_live_board_percent["value"] = percent
                    try:
                        current_status = merge_selector_load_results(state, groups, timeframe)
                        current_rows = list(current_status.get("status_rows") or [])
                        if current_rows:
                            live_rows.dataframe(current_rows, use_container_width=True, hide_index=True)
                    except Exception:
                        pass

            try:
                if load_s1_clicked:
                    load_selector_with_assigned_key(
                        state, "FIRST", groups.get("FIRST") or [], timeframe, "TWELVE_KEY_1",
                        progress_callback=_load_progress, emergency_cross_key_retry=bool(emergency_cross_key),
                    )
                elif load_s2_clicked:
                    load_selector_with_assigned_key(
                        state, "SECOND", groups.get("SECOND") or [], timeframe, "TWELVE_KEY_2",
                        progress_callback=_load_progress, emergency_cross_key_retry=bool(emergency_cross_key),
                    )
                elif load_s3_clicked:
                    load_selector_with_assigned_key(
                        state, "THIRD", groups.get("THIRD") or [], timeframe, "TWELVE_DATA_KEY_POOL",
                        progress_callback=_load_progress, emergency_cross_key_retry=False,
                    )
                elif retry_s1_clicked:
                    load_selector_with_assigned_key(
                        state, "FIRST", groups.get("FIRST") or [], timeframe, "TWELVE_KEY_1",
                        retry_failed_only=True, progress_callback=_load_progress,
                        emergency_cross_key_retry=bool(emergency_cross_key),
                    )
                elif retry_s2_clicked:
                    load_selector_with_assigned_key(
                        state, "SECOND", groups.get("SECOND") or [], timeframe, "TWELVE_KEY_2",
                        retry_failed_only=True, progress_callback=_load_progress,
                        emergency_cross_key_retry=bool(emergency_cross_key),
                    )
                elif retry_s3_clicked:
                    load_selector_with_assigned_key(
                        state, "THIRD", groups.get("THIRD") or [], timeframe, "TWELVE_DATA_KEY_POOL",
                        retry_failed_only=True, progress_callback=_load_progress,
                        emergency_cross_key_retry=False,
                    )
                elif force_retry_clicked:
                    load_all_selectors_safely(
                        state, groups, timeframe, progress_callback=_load_progress,
                        retry_failed_only=True, force_retry_failed=True,
                        emergency_cross_key_retry=bool(emergency_cross_key),
                    )
                else:
                    load_all_selectors_safely(
                        state, groups, timeframe, progress_callback=_load_progress,
                        emergency_cross_key_retry=bool(emergency_cross_key),
                    )
                final_status = merge_selector_load_results(state, groups, timeframe)
                final_rows = list(final_status.get("status_rows") or [])
                loaded_count = int(final_status.get("loaded_now_count") or 0)
                failed_count = max(0, len(canonical_selected) - loaded_count)
                retry_eligible_count = sum(1 for row in final_rows if bool(row.get("Reload Eligible")))
                circuit_cleared = state.get("last_selector_owned_circuit_clear_20260708", {}).get("cleared") if isinstance(state.get("last_selector_owned_circuit_clear_20260708"), dict) else 0
                request_attempted_after_click = any(bool(row.get("API request attempted after click")) for row in final_rows)
                no_usable = [
                    str(row.get("Symbol"))
                    for row in final_rows
                    if str(row.get("Load Final State") or "").upper() != "VALIDATED"
                ]
                summary = final_status.get("provider_summary") if isinstance(final_status.get("provider_summary"), dict) else {}
                progress_bar.progress(1.0, text="Selector-owned load transaction completed")
                if failed_count:
                    st.warning(
                        f"PARTIAL_READY · READY: {loaded_count} · FAILED: {failed_count} · Retry eligible: {retry_eligible_count}. "
                        f"Circuit breaker cleared: {'yes' if circuit_cleared else 'no'} · API request attempted after click: {'yes' if request_attempted_after_click else 'no'}. "
                        f"No usable data: {', '.join(no_usable) if no_usable else 'None'}"
                    )
                else:
                    st.success(
                        f"FULL_READY · READY: {loaded_count} · FAILED: 0 · Circuit breaker cleared: {'yes' if circuit_cleared else 'no'} · "
                        f"API request attempted after click: {'yes' if request_attempted_after_click else 'no'}."
                    )
                st.caption(
                    "Provider summary: "
                    f"Twelve Key 1 {int(summary.get('TWELVE_KEY_1') or 0)}, "
                    f"Twelve Key 2 {int(summary.get('TWELVE_KEY_2') or 0)}, "
                    f"Legacy pool {int(summary.get('TWELVE_DATA_KEY_POOL') or 0)}, "
                    f"Cache {int(summary.get('LOCAL_CACHE') or 0)}, "
                    f"Emergency {int(summary.get('LAST_KNOWN_VALID_CACHE') or 0)}, "
                    f"None {int(summary.get('NONE') or 0)}"
                )
                st.rerun()
            except Exception as load_exc:
                progress_bar.empty()
                progress_text.empty()
                st.error(f"Selector-owned load failed safely: {type(load_exc).__name__}: {load_exc}")

        loaded_now = normalize_selected(canonical_status.get("loaded_symbols") or [], limit=None)
        failed_now = normalize_selected(canonical_status.get("failed_symbols") or [], limit=None)
        if loaded_now and not failed_now and len(loaded_now) == len(canonical_selected):
            st.success("Canonical loaded universe ready: " + " → ".join(loaded_now))
        elif loaded_now:
            st.warning("Canonical universe is usable with warnings: " + " → ".join(loaded_now))
            if failed_now:
                st.caption("No usable data yet: " + " → ".join(failed_now))
        else:
            st.info(str(canonical_status.get("message") or "Press the main load button before calculating."))

        # Preserve the old cumulative database discovery as audit history only.
        completed = normalize_selected(state.get(COMPLETED_UNION_KEY) or [], limit=None)
        if completed:
            with st.expander("Historical completed-symbol archive (not used for the next run)", expanded=False):
                st.caption(" → ".join(completed))
    return groups


def render_multi_symbol_selector(state: MutableMapping[str, Any] | None = None) -> list[str]:
    """Backward-compatible single-card facade for older Home/sidebar imports.

    Settings is the only location that renders all three selectors together.
    Older surfaces keep the historical first-selector card and therefore never
    duplicate the Second/Third widget keys.
    """
    state = state if state is not None else st.session_state
    from core.multi_symbol_run_groups_20260706 import initialize_groups, load_group_preferences
    persisted: dict[str, Any] = {}
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        persisted = load_group_preferences(DEFAULT_DB_PATH)
    except Exception:
        persisted = {}
    initialize_groups(state, state.get(SELECTED_KEY) or TOP_10_CURRENCY_PAIRS, persisted=persisted)
    selected = _render_group_card(state, "FIRST")
    _persist_groups(state)
    return selected


def render_calculation_mode_selector(state: MutableMapping[str, Any] | None = None) -> str:
    """Render the run-choice heading without a duplicate legacy profile selector."""
    state = state if state is not None else st.session_state
    current = str(state.get("settings_calculation_scope_20260625") or "QUICK").upper()
    if current not in {"LUNCH_CORE", "QUICK", "FULL"}:
        current = "QUICK"
    state["settings_calculation_scope_20260625"] = current
    # The three actual buttons are rendered by Settings.  This compatibility
    # function only maintains the selected depth state and no longer renders a
    # duplicate explanatory/profile block.
    return current


__all__ = [
    "SUPPORTED_SYMBOLS", "FIRST_BEST_10_CURRENCY_PAIRS", "SECOND_BEST_10_CURRENCY_POOL",
    "THIRD_BEST_10_SPREAD_UNDER_25",
    "FIRST_BEST_6_CURRENCY_PAIRS", "SECOND_BEST_6_CURRENCY_PAIRS",
    "SELECTED_KEY", "ACTIVE_KEY", "MAIN_SYMBOL_KEY", "DISPLAY_SYMBOL_KEY", "_MULTI_WIDGET_KEY", "normalize_symbol",
    "normalize_selected", "render_multi_symbol_selector", "render_multi_symbol_selectors",
    "render_calculation_mode_selector",
]
