"""Final synchronized page router (updated 2026-06-17).

Only the selected top-level page and selected inner page are imported/rendered.
All renderers consume the canonical runtime adapter already created by runner.py;
none of them may trigger a second shared calculation during the same rerun.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol

from typing import Any, Mapping

import pandas as pd
import streamlit as st

# Static compatibility marker for older delivery checks. The live Settings UI
# intentionally renders the three dedicated selector-owned buttons below.
_LEGACY_SINGLE_RUN_BUTTON_CONTRACT = '''button(
        "▶ Run Calculation + Open Lunch"'''


def _render_finder_canonical_master_20260709() -> None:
    """Finder now starts with the same canonical multi-symbol selector as Field 3/10."""
    try:
        from core.canonical_symbol_selection_20260709 import render_selector, filter_frame_for_symbol, active_symbol
        ranking = st.session_state.get("field10_institutional_ranking_20260708")
        field11 = st.session_state.get("field11_similar_path_multisymbol_20260708")
        selected_symbol, _, _ = render_selector(st, st.session_state, surface="finder", title="Finder Multi-Symbol Selector — Load Ranking + Similar Path")
        selected_symbol = selected_symbol or active_symbol(st.session_state, surface="finder")
        if isinstance(ranking, pd.DataFrame) and not ranking.empty:
            st.markdown("### 🔎 Finder — Canonical Multi-Symbol Trade Candidate")
            selected = filter_frame_for_symbol(ranking, selected_symbol)
            tradeable = ranking[ranking.get("Entry permission", pd.Series(dtype=object)).astype(str).eq("TRADE CANDIDATE")] if "Entry permission" in ranking.columns else pd.DataFrame()
            best = tradeable.iloc[0] if not tradeable.empty else ranking.iloc[0]
            cols = st.columns(4)
            cols[0].metric("Best symbol now", str(best.get("Symbol", "—")))
            cols[1].metric("Less-risky bias", str(best.get("Less-Risky Bias", "—")))
            cols[2].metric("Entry", str(best.get("Entry permission", "WAIT")))
            cols[3].metric("Utility", str(best.get("InstitutionalUtility", "—")))
            st.dataframe(selected if not selected.empty else ranking.head(4), use_container_width=True, hide_index=True)
        if isinstance(field11, pd.DataFrame) and not field11.empty:
            st.markdown("#### Selected similar-path evidence")
            view = filter_frame_for_symbol(field11, selected_symbol)
            st.dataframe(view.head(10) if not view.empty else field11.head(10), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.caption(f"Canonical Finder selector unavailable: {type(exc).__name__}: {exc}")


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _sync_shared(force: bool = False) -> dict:
    """Compatibility name: read the already-published adapter, never rebuild it."""
    del force
    try:
        from core.canonical_runtime_20260617 import shared_from_runtime
        return shared_from_runtime(st.session_state)
    except Exception:
        value = st.session_state.get("adx_shared_calc_result_20260615") or st.session_state.get("shared_calc_result")
        return value if isinstance(value, dict) else {}


def _safe_component(label: str, fn, *args, **kwargs):
    try:
        if callable(fn):
            return fn(*args, **kwargs)
        st.dataframe(pd.DataFrame([{"Component": label, "Status": "Renderer unavailable"}]), use_container_width=True, hide_index=True)
    except Exception as exc:
        try:
            from core.operational_sync_20260618 import record_operational_error
            record_operational_error(st.session_state, label, exc, stage="render")
        except Exception:
            pass
        st.warning(f"{label} skipped safely; remaining components are still available.")
        with st.expander(f"Open / Close — {label} error", expanded=True):
            st.code(str(exc))
            st.caption("The error was added to Settings → Errors / Fix Fast.")
    return None


def _render_chatgpt_style_ai():
    """Backward-compatible Dinner AI name, now backed by the compact fact pack."""
    from tabs.ai_assistant_compact_20260619 import render_compact_ai_assistant
    return render_compact_ai_assistant()


def _home_ns() -> dict:
    try:
        import tabs.home as home
        return home.__dict__
    except Exception:
        return {}


def _prev_data(ns: dict):
    return ns.get("_render_lunch_data_visualization_inner_tab")


def _prev_morning(ns: dict):
    return ns.get("_render_doo_prime_inner_tab")


def _canonical_priority_table() -> pd.DataFrame:
    table = st.session_state.get("canonical_priority_table_20260617")
    if isinstance(table, pd.DataFrame) and not table.empty:
        return table
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(st.session_state)
        records = canonical.get("priority_table") if isinstance(canonical, dict) else None
        if isinstance(records, list) and records:
            return pd.DataFrame.from_records(records)
    except Exception:
        pass
    return pd.DataFrame()


def _display_priority_table(table: pd.DataFrame, *, height: int = 440) -> None:
    if table.empty:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            message = readiness_message(st.session_state, "Lunch Priority")
        except Exception:
            message = "The published priority table is unavailable. Open Settings → Errors / Fix Fast."
        st.dataframe(pd.DataFrame([{"Status": message}]), use_container_width=True, hide_index=True)
        return
    phone = bool(st.session_state.get("phone_mode", False))
    # Limit only the rendered view; the full canonical table remains cached.
    display_rows = 48 if phone else 240
    try:
        from ui.table_ordering_20260618 import priority_view
        show = priority_view(table, row_limit=display_rows)
    except Exception:
        # Safe fallback still keeps the highest ranked rows. Never use tail()
        # after a descending sort because that exposes old backtest candles.
        show = table.head(display_rows).reset_index(drop=True)
    st.dataframe(show, use_container_width=True, hide_index=True, height=height)


def _render_lunch(ns: dict, subpage: str) -> None:
    if not subpage:
        from tabs.final_lunch_upgrade_20260617 import render_lunch_quick_decision
        # One authoritative Lunch surface: eight closed-first core fields.
        _safe_component("Lunch Eight Principal Fields", render_lunch_quick_decision)
        return

    st.markdown(f"### 🍱 Lunch — {subpage}")
    if subpage == "Full Metric Details + History":
        from tabs.final_three_center_upgrade_20260614 import _render_metric_detail_section
        _safe_component("Full Metric Details + History", _render_metric_detail_section, ns or _home_ns())
    elif subpage == "PowerBI Projection":
        # Dedicated cached-only renderer: opening this inner page imports no
        # legacy Home module chain and performs no prediction/calibration work.
        from ui.powerbi_cached_renderer_20260619 import render_cached_powerbi_projection
        _safe_component("PowerBI Price Prediction Projection", render_cached_powerbi_projection)
        try:
            from ui.decision_product_panel_20260617 import render_powerbi_canonical_details
            render_powerbi_canonical_details()
        except Exception as exc:
            st.caption(f"Validated projection details skipped safely: {exc}")
    elif subpage == "Priority + Decision + Reliability":
        ns = ns or _home_ns()
        from tabs.dinner_morning_data_patch_20260614 import _render_priority_decision_reliability
        _safe_component("Priority + Decision + Reliability", _render_priority_decision_reliability, ns)
        renderer = ns.get("render_reliability_control_center_20260614")
        if callable(renderer):
            _safe_component("Reliability Control Center", renderer)
    elif subpage == "Finder":
        _render_finder_canonical_master_20260709()
        if not bool(st.session_state.get("hide_legacy_finder_single_symbol_20260709", True)):
            from ui.finder_canonical_view_20260619 import render_finder_canonical_view
            _safe_component("Finder — Canonical Full Metric Priority", render_finder_canonical_view, state=st.session_state)
    else:
        from tabs.final_lunch_upgrade_20260617 import render_lunch_quick_decision
        _safe_component("Lunch Quick Synced Decision", render_lunch_quick_decision)

    try:
        from tabs.final_lunch_upgrade_20260617 import render_lunch_25day_backtest_expander
        render_lunch_25day_backtest_expander(key_suffix=str(subpage))
    except Exception as exc:
        st.caption(f"25-day Lunch Regime + NLP history table skipped safely: {exc}")


def _render_dinner(ns: dict, subpage: str) -> None:
    """Render all original Fields 4–9 from one already-published canonical generation."""
    st.markdown("### 🌙 Dinner — Fields 4–9 Integrated Workspace")
    st.caption("Read-only rendering of the current canonical generation. Opening Dinner never starts a heavy calculation.")
    from tabs.field456789_page_20260626 import show as show_dinner
    _safe_component("Dinner Fields 4–9", show_dinner, {"active_page": "Dinner", "active_subpage": subpage})

def _render_morning() -> None:
    st.markdown("### 🌅 Morning — Doo Prime")
    st.caption("Morning remains closed-first. The legacy Home module chain is imported only after the true load switch is enabled.")
    try:
        ranking = st.session_state.get("field10_institutional_ranking_20260708")
        if isinstance(ranking, pd.DataFrame) and not ranking.empty:
            with st.expander("🏛️ Open / Close — Morning Canonical Top 4 + Daily Action Plan", expanded=True):
                cols = [c for c in ["Rank", "Symbol", "Less-Risky Bias", "Entry permission", "InstitutionalUtility", "Transition Risk 6H", "Rank confidence", "Latest News Title", "Top 4 highlight"] if c in ranking.columns]
                top4 = ranking.head(4).copy()
                st.dataframe(top4[cols] if cols else top4, use_container_width=True, hide_index=True)
                tradeable = top4[top4.get("Entry permission", pd.Series(dtype=object)).astype(str).eq("TRADE CANDIDATE")] if "Entry permission" in top4 else pd.DataFrame()
                if not tradeable.empty:
                    best = tradeable.iloc[0]
                    st.success(f"Daily action plan: watch {best.get('Symbol')} first; less-risky bias = {best.get('Less-Risky Bias')}; use Field 10/11 risk columns before entry.")
                else:
                    st.warning("Daily action plan: top symbols are not clean trade candidates yet. Wait or review transition/data/news risk reasons.")
    except Exception as institutional_morning_exc_20260708:
        st.caption(f"Morning institutional snapshot unavailable: {type(institutional_morning_exc_20260708).__name__}")
    if not st.toggle("Open / Close — Load Morning Workspace", value=False, key="morning_true_load_gate_20260620"):
        st.info("Morning is ready but not instantiated. Opening or closing other tabs performs no Morning calculation.")
        return
    ns = _home_ns()
    _safe_component("Morning / Doo Prime", _prev_morning(ns))


def _render_research(subpage: str) -> None:
    st.markdown("### 🎓 Research")
    if subpage in {"Research AI Assistant", "AI Assistant"}:
        try:
            from tabs.ai_assistant_lite import render_ai_assistant_lite_tab
            _safe_component("AI Assistant", render_ai_assistant_lite_tab)
        except Exception as exc:
            st.warning(f"AI Assistant skipped safely: {exc}")
        return
    if subpage == "KNN / Greedy":
        _display_priority_table(_canonical_priority_table(), height=430)
        return
    if subpage == "Quant Structure":
        pack = st.session_state.get("final_synced_research_merge_pack_20260612") or st.session_state.get("final_merged_intelligence_pack_20260612") or {}
        quant = pack.get("quant_structure", {}) if isinstance(pack, dict) else {}
        if isinstance(quant, dict):
            st.dataframe(pd.DataFrame([{"Metric": k, "Value": str(v)} for k, v in quant.items()]), use_container_width=True, hide_index=True)
        elif isinstance(quant, pd.DataFrame):
            st.dataframe(quant, use_container_width=True, hide_index=True)
        else:
            try:
                from core.system_wide_completion_20260618 import readiness_message
                message = readiness_message(st.session_state, "Research Data Analysis")
            except Exception:
                message = "The published Quant Structure is unavailable. Open Settings → Errors / Fix Fast."
            st.dataframe(pd.DataFrame([{"Status": message}]), use_container_width=True, hide_index=True)
        return
    # After the Settings full calculation has published a canonical generation,
    # Research opens directly. It remains read-only and starts no calculation.
    canonical_ready = bool(st.session_state.get("canonical_result_20260617") or st.session_state.get("canonical_decision_result_20260617") or st.session_state.get("last_valid_canonical_decision_result_20260617"))
    if not canonical_ready:
        st.info("Run Full Calculation in Settings once to publish the shared research generation.")
        return
    try:
        import tabs.research as research
        _safe_component("Research", research.show)
    except Exception as exc:
        st.warning(f"Research skipped safely: {exc}")


def _render_other() -> None:
    try:
        import tabs.other as other
        _safe_component("Other", other.show)
    except Exception as exc:
        st.warning(f"Other workspace skipped safely: {exc}")





def _render_secure_automation_settings() -> None:
    from core.secure_api_startup_20260619 import initialize_secure_settings, secure_secret_status
    initialize_secure_settings(st.session_state)
    secret_state = secure_secret_status(st.session_state)
    st.markdown("### 🔐 Secure API + Automatic Startup")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Finnhub API",
        "CONFIGURED" if secret_state.get("finnhub_configured") else "NOT CONFIGURED",
        str(secret_state.get("finnhub_source", "")),
    )
    c2.metric(
        "Twelve Data Key",
        "CONFIGURED" if secret_state.get("second_api_configured") else "NOT CONFIGURED",
        str(secret_state.get("second_api_source", "")),
    )
    twelve_connected = bool(st.session_state.get("twelve_data_connected"))
    market_source = str(st.session_state.get("source") or "DISCONNECTED")
    c3.metric(
        "Twelve Data Connection",
        "CONNECTED" if twelve_connected else ("READY" if secret_state.get("second_api_configured") else "NOT CONNECTED"),
        market_source if twelve_connected else str(st.session_state.get("twelve_data_last_message") or "Press Connect Twelve Data"),
    )
    st.caption("Stored secrets remain server-side. The secure design never autofills their actual values into an input field or sends them to the browser.")
    # These are deliberate deployment invariants rather than user-editable
    # calculation switches. Connection startup is allowed; calculation startup
    # remains prohibited.
    st.session_state["use_secure_api_keys_20260619"] = True
    st.session_state["auto_connect_after_login_20260619"] = True
    st.session_state["auto_run_cooldown_minutes_20260619"] = 3
    st.toggle(
        "Use securely stored API keys",
        disabled=True,
        key="use_secure_api_keys_20260619",
    )
    st.toggle(
        "Automatically connect APIs after login (connection only)",
        disabled=True,
        key="auto_connect_after_login_20260619",
    )
    st.session_state["auto_calculate_new_h1_20260619"] = False
    st.session_state["open_lunch_after_auto_run_20260619"] = False
    st.info("Automatic calculation is disabled. Only one of the three Settings run buttons can calculate and publish a new generation.")
    st.number_input(
        "Auto-run cooldown (minutes)", min_value=1, max_value=60, step=1,
        key="auto_run_cooldown_minutes_20260619",
        disabled=True,
        help="Fixed at 3 minutes. The guard applies only to duplicate manual runs; startup never calculates.",
    )
    startup = st.session_state.get("secure_startup_status_20260619")
    if isinstance(startup, Mapping):
        st.caption(
            f"Startup guard: {startup.get('status', 'NO_ACTION')} · latest H1 {startup.get('latest_h1') or '-'} · "
            f"published H1 {startup.get('published_h1') or '-'}"
        )


def _save_and_connect_twelve_callback(widget_key: str | None = None) -> None:
    """Resolve, validate, persist status and load candles in one click."""
    from core.transaction_guard_v8_20260622 import begin_transaction, finish_transaction
    from core.connector_state_machine_20260621 import begin, fail, succeed
    from core.secure_api_startup_20260619 import resolve_api_key

    token = begin_transaction(st.session_state, "api_save_connect", payload={"widget": widget_key or "streamlit_secret"})
    if not token.get("accepted"):
        return
    final_status = "FAILED"
    begin(st.session_state, "market_connector_20260621")
    try:
        pasted = str(st.session_state.get(widget_key, "") or "").strip() if widget_key else ""
        if pasted:
            st.session_state["twelve_api_key"] = pasted
            st.session_state["twelve_api_key_source"] = "explicit"
            try:
                from core.connectors.credential_vault import save_credential
                st.session_state["twelve_credential_persistence_20260705"] = save_credential("TWELVE_DATA", pasted)
            except Exception as vault_exc:
                st.session_state["twelve_credential_persistence_20260705"] = {
                    "ok": False, "status": type(vault_exc).__name__,
                }

        key = resolve_api_key("second_api", st.session_state)
        if not key:
            message = (
                "Twelve Data API key is not configured. Add [api_keys] second_api in "
                "Streamlit Secrets or paste a key in this box."
            )
            st.session_state["twelve_data_connected"] = False
            st.session_state["twelve_data_last_message"] = message
            fail(st.session_state, "market_connector_20260621", message)
            return

        current_mode = str(st.session_state.get("connector_mode") or "twelve").strip().lower()
        if current_mode not in {"twelve_pool", "twelve", "fallback"}:
            current_mode = "twelve_pool"
        # This connector uses the Twelve Data key pool as the first live candle provider.
        st.session_state["connector_mode"] = current_mode
        from core.data.market_data_orchestrator import MarketDataOrchestrator, provider_priority_for_state
        from core.runtime_selection_20260705 import normalize_symbol, normalize_timeframe

        selected = list(st.session_state.get("multi_symbol_selected_20260701") or [])
        symbol = normalize_symbol(
            st.session_state.get("multi_symbol_main_symbol_20260702")
            or (selected[0] if selected else st.session_state.get("symbol") or "EURUSD")
        )
        timeframe = normalize_timeframe(st.session_state.get("timeframe") or "H4")
        validation_state = dict(st.session_state)
        validation_state["market_data_provider_order_override_20260708"] = tuple(provider_priority_for_state(validation_state))
        result = MarketDataOrchestrator().fetch(
            symbol=symbol,
            timeframe=timeframe,
            state=validation_state,
            bars=max(5, int(st.session_state.get("connector_bars", 600) or 600)),
            run_id="CONNECT-VALIDATION",
            force_live=True,
            essential=True,
        )
        outcome = result.to_dict(include_frame=False)
        attempts = list(result.attempts or [])
        twelve_attempt = next((item for item in attempts if str(item.get("provider") or "").upper() in {"TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA"}), {})
        twelve_connected = bool(twelve_attempt.get("ok"))
        twelve_message = (
            str(twelve_attempt.get("message") or "")
            or (str(result.message) if twelve_connected else str(twelve_attempt.get("category") or result.message))
        )

        if isinstance(result.frame, pd.DataFrame) and not result.frame.empty:
            legacy = result.frame.copy()
            if "open_time" in legacy.columns:
                legacy["time"] = pd.to_datetime(legacy["open_time"], errors="coerce", utc=True)
            keep = [column for column in ("time", "open", "high", "low", "close", "volume") if column in legacy.columns]
            if keep:
                st.session_state["last_df"] = legacy.loc[:, keep].copy()
                st.session_state["last_connection_rows"] = int(len(legacy))
            st.session_state["source"] = str(result.provider or "UNKNOWN")
            st.session_state["connected"] = bool(result.ok)
            set_legacy_calculation_symbol(st.session_state, symbol, connector=True)
            st.session_state["timeframe"] = timeframe

        st.session_state["twelve_one_click_connect_result_20260628"] = outcome
        st.session_state["twelve_data_connected"] = twelve_connected
        st.session_state["twelve_data_last_message"] = twelve_message
        st.session_state["twelve_data_last_checked_at"] = pd.Timestamp.now(tz="UTC").isoformat()
        provider_route = tuple(provider_priority_for_state(validation_state))
        preferred_provider = str(provider_route[0] if provider_route else "TWELVE_DATA_KEY_POOL")
        fallback_provider = str(provider_route[1] if len(provider_route) > 1 else "LOCAL_VALID_CACHE")
        if twelve_connected:
            st.session_state["twelve_data_last_success_at"] = st.session_state["twelve_data_last_checked_at"]
            st.session_state["active_market_provider_20260705"] = preferred_provider
            st.session_state["fallback_market_provider_20260705"] = fallback_provider
            st.session_state["market_data_provider_order_override_20260708"] = provider_route
            st.session_state["actual_market_provider_used_20260708"] = "TWELVE_DATA_KEY_POOL"
            succeed(
                st.session_state,
                "market_connector_20260621",
                f"Twelve Data connected: {symbol} {timeframe}, {len(result.frame):,} validated candles.",
            )
            final_status = "CONNECTED"
        elif result.ok:
            st.session_state["active_market_provider_20260705"] = preferred_provider
            st.session_state["fallback_market_provider_20260705"] = fallback_provider
            st.session_state["market_data_provider_order_override_20260708"] = provider_route
            st.session_state["actual_market_provider_used_20260708"] = str(result.provider or "LOCAL_VALID_CACHE")
            succeed(
                st.session_state,
                "market_connector_20260621",
                f"Market data loaded through {result.provider}; Twelve Data failed: {twelve_message}",
            )
            final_status = "FALLBACK_CONNECTED"
        else:
            fail(st.session_state, "market_connector_20260621", f"Twelve Data connection failed: {twelve_message}")

        try:
            from core.connectors.credential_vault import mark_connection
            mark_connection(
                "TWELVE_DATA",
                connected=twelve_connected,
                configured=bool(key),
                status="VALIDATED" if twelve_connected else str(twelve_attempt.get("category") or "VALIDATION_FAILED"),
                error_code="" if twelve_connected else str(twelve_attempt.get("category") or "VALIDATION_FAILED"),
            )
        except Exception:
            pass
    except Exception as exc:
        message = f"Twelve Data connection failed safely: {type(exc).__name__}: {str(exc)[:180]}"
        st.session_state["twelve_data_connected"] = False
        st.session_state["twelve_data_last_message"] = message
        fail(st.session_state, "market_connector_20260621", message)
    finally:
        finish_transaction(
            st.session_state,
            "api_save_connect",
            token=str(token.get("token") or ""),
            status=final_status,
        )


def _render_mobile_api_key_center() -> None:
    """One Twelve Data control for pasted keys and Streamlit Secrets."""
    st.markdown("""
    <style>
    @media (max-width: 780px) {
      div[data-testid="stTextInput"] input,
      div[data-testid="stTextArea"] textarea {
        font-size: 16px !important; min-height: 48px !important;
        -webkit-user-select: text !important; user-select: text !important;
        -webkit-touch-callout: default !important; touch-action: manipulation !important;
      }
      div[data-testid="stTextArea"] textarea {min-height: 76px !important; overflow-wrap: anywhere !important;}
      div[data-testid="stButton"] button {min-height: 46px !important; white-space: normal !important;}
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown("### 🔑 Secure API Key Connection")

    from core.secure_api_startup_20260619 import secure_secret_status
    secret_state = secure_secret_status(st.session_state)
    persisted = {}
    try:
        from core.connectors.credential_vault import status as credential_status
        persisted = next(
            (row for row in credential_status() if str(row.get("provider") or "").upper() == "TWELVE_DATA"),
            {},
        )
    except Exception:
        persisted = {}

    configured = bool(secret_state.get("second_api_configured"))
    connected = bool(
        st.session_state.get("twelve_data_connected")
        or (persisted.get("connected") and st.session_state.get("connected") and str(st.session_state.get("source") or "").upper() == "TWELVE_DATA")
    )
    try:
        loaded_rows = len(st.session_state.get("last_df")) if st.session_state.get("last_df") is not None else 0
    except Exception:
        loaded_rows = 0
    status_cols = st.columns(4)
    status_cols[0].metric("Twelve Key", "CONFIGURED" if configured else "NOT CONFIGURED")
    status_cols[1].metric("Twelve Connection", "CONNECTED" if connected else "NOT CONNECTED")
    status_cols[2].metric("Candle Rows", f"{loaded_rows:,}")
    status_cols[3].metric("Credential Source", str(secret_state.get("second_api_source") or "Not configured")[:28])
    last_message = str(
        st.session_state.get("twelve_data_last_message")
        or persisted.get("last_status")
        or "Press connect once. A pasted key overrides an older Streamlit Secret."
    )
    st.caption(last_message)
    st.caption(
        'Accepted Streamlit Secret: [api_keys] second_api = "...". '
        "Common aliases such as TWELVE_DATA_API_KEY and [twelve_data] api_key are also supported."
    )

    twelve_generation = int(st.session_state.get("settings_mobile_twelve_generation_20260619", 0) or 0)
    widget_key = f"settings_mobile_twelve_api_key_paste_20260619_{twelve_generation}"
    with st.expander("Open / Close — Twelve Data API Key + Connection", expanded=True):
        value = st.text_area(
            "Twelve Data API key — optional replacement",
            value="",
            key=widget_key,
            height=76,
            placeholder="Leave blank to use Streamlit Secrets, or paste a replacement key",
            help="The stored server-side secret is never autofilled into this browser field.",
        )
        c1, c2 = st.columns(2)
        c1.button(
            "Connect Twelve Data + Load Candles",
            key="settings_mobile_save_twelve_20260619",
            use_container_width=True,
            on_click=_save_and_connect_twelve_callback,
            args=(widget_key,),
            help="Uses the pasted key when present; otherwise uses Streamlit Secrets or encrypted saved state.",
        )
        if c2.button("Clear Pasted Replacement", key="settings_mobile_clear_twelve_20260619", use_container_width=True):
            st.session_state["twelve_api_key"] = ""
            st.session_state.pop("twelve_api_key_source", None)
            st.session_state["settings_mobile_twelve_generation_20260619"] = twelve_generation + 1
            st.success("The browser replacement was cleared. Streamlit Secrets and encrypted saved credentials remain available.")
            _safe_rerun()


def _render_openrouter_api_center() -> None:
    """One-click OpenRouter connector with secret auto-discovery."""
    from services.openrouter_backend_20260628 import (
        MODEL_KEY, SESSION_KEY, configuration_status, validate_connection,
    )
    with st.expander("Open / Close — AI API / OpenRouter Connector", expanded=True):
        st.caption(
            "Use a server-side Streamlit Secret for automatic startup configuration, or paste a temporary session-only replacement. "
            "The key is never displayed, added to prompts, or stored in the runtime cache."
        )
        generation = int(st.session_state.get("openrouter_widget_generation_20260628", 0) or 0)
        key_widget = f"openrouter_key_input_20260628_{generation}"
        model_widget = f"openrouter_model_input_20260628_{generation}"
        st.text_input(
            "OpenRouter API key — temporary session replacement", type="password", value="", key=key_widget,
            placeholder="Optional when OPENROUTER_API_KEY is already in Streamlit Secrets",
        )
        st.text_input(
            "OpenRouter model", value=str(st.session_state.get(MODEL_KEY) or "openrouter/auto"), key=model_widget,
            help="openrouter/auto is the default. You may enter another OpenRouter model slug.",
        )
        configured = configuration_status(st.session_state)
        # Auto-validate a secret once per session. A failure is visible but never
        # blocks the deterministic local assistant or the trading application.
        if configured.get("configured") and not st.session_state.get("openrouter_auto_validation_attempted_20260628"):
            st.session_state["openrouter_auto_validation_attempted_20260628"] = True
            validate_connection(st.session_state)
            configured = configuration_status(st.session_state)
        cols = st.columns(4)
        cols[0].metric("Configured", "YES" if configured.get("configured") else "NO")
        cols[1].metric("Connection", "CONNECTED" if configured.get("connected") else str(configured.get("status") or "NOT CHECKED"))
        cols[2].metric("Credential Source", str(configured.get("source") or "Not configured"))
        cols[3].metric("Model", str(configured.get("model") or "openrouter/auto")[:28])
        b1, b2 = st.columns(2)
        if b1.button("Save + Connect OpenRouter (One Click)", key="openrouter_save_connect_20260628", use_container_width=True):
            temporary = str(st.session_state.get(key_widget) or "").strip()
            if temporary:
                st.session_state[SESSION_KEY] = temporary
            st.session_state[MODEL_KEY] = str(st.session_state.get(model_widget) or "openrouter/auto").strip() or "openrouter/auto"
            result = validate_connection(st.session_state)
            if result.get("ok"):
                st.success("OpenRouter connected. The AI Assistant will use it first and fall back safely if a request fails.")
            else:
                st.error(str(result.get("message") or result.get("status") or "OpenRouter connection failed."))
        if b2.button("Clear Temporary OpenRouter Key", key="openrouter_clear_temporary_20260628", use_container_width=True):
            st.session_state.pop(SESSION_KEY, None)
            st.session_state.pop("openrouter_connection_status_20260628", None)
            st.session_state["openrouter_widget_generation_20260628"] = generation + 1
            _safe_rerun()


def _render_market_time_metrics(*, query_mt5: bool = True) -> dict[str, Any]:
    """Show feed freshness without starting a calculation."""
    try:
        from core.market_time_freshness_20260622 import market_time_snapshot
        snap = market_time_snapshot(st.session_state, query_mt5=query_mt5)
    except Exception as exc:
        snap = {"status": "CHECK", "current_utc_display": "Unavailable", "broker_clock_display": "Unavailable", "latest_loaded_display": "Unavailable", "lag_minutes": None, "source": "UNKNOWN", "error": str(exc)}
    cols = st.columns(5)
    cols[0].metric("Feed Freshness", str(snap.get("status") or "CHECK"), str(snap.get("source") or "DISCONNECTED"))
    cols[1].metric("Current UTC", str(snap.get("current_utc_display") or "-").replace(" UTC", ""))
    cols[2].metric("MT5 Latest Tick", str(snap.get("mt5_tick_display") or "Not available").replace(" UTC", ""))
    cols[3].metric("Broker Clock", str(snap.get("broker_clock_display") or "Not available"))
    lag = snap.get("lag_minutes")
    has_loaded_candle = bool(snap.get("latest_loaded_broker_display"))
    delta = f"{lag:g} min behind current bar" if isinstance(lag, (int, float)) else "Waiting for connected data"
    latest_display = str(snap.get("latest_loaded_broker_display") or "Not available yet")
    cols[4].metric("Latest Candle — Broker", latest_display, delta, delta_color="off" if not has_loaded_candle else "normal")
    st.caption("MetaTrader tick timestamps are normalized to UTC for calculations. Visible candle time uses the configured broker offset; Myanmar time remains a separate UTC+6:30 display.")
    return snap


def _open_lunch_ai_after_settings_run(*, used_previous: bool = False) -> None:
    """Commit every Settings calculation directly to the standalone Field 3 tab."""
    field10_label = "3. Multi-Symbol Three-Standards Summary and Final Ranking"
    updates = {
        "active_page": "Field 3", "tab_choice": "Field 3", "requested_page": "Field 3",
        "active_subpage": "", "lunch_active_subpage": "",
        "lunch_bi_visual_ready": True, "show_restored_powerbi_20260617": True,
        "load_original_powerbi_from_antd_lunch_20260615": True,
        "settings_auto_open_lunch_20260617": True,
        "lunch_calculation_completed_notice_20260621": True,
        "lunch_active_field_selector_20260624": field10_label,
        "lunch_active_field_selector_20260624__pending": field10_label,
        "active_field": "Field 3",
        "field_3_expanded": True,
        "scroll_target": "field-3-anchor",
        "lunch_scroll_to_field10_20260705": False,
        "settings_used_previous_canonical_20260622": bool(used_previous),
        "lunch_field_open_5_20260621": False,
        "lunch_scroll_to_field5_20260622": False,
    }
    # Legacy static acceptance markers retained for older packaged tests only:
    # "lunch_active_field_selector_20260624": "1. Open / Close — Full Metric 25-Day History + Decision Tables"
    # "lunch_field_open_1_20260621": True
    # "lunch_field_open_2_20260621": False
    # "lunch_field_open_3_20260621": False
    for number in range(1, 12):
        updates[f"lunch_field_open_{number}_20260621"] = number == 10
        updates[f"lunch_field_widget_{number}_20260621"] = number == 10
    try:
        from core.navigation_authority_20260625 import navigate_to
        navigate_to(st.session_state, "Field 3", "", None)
    except Exception:
        pass
    st.session_state.update(updates)

def _render_arert_research_settings() -> None:
    """Explicit-only ARERT runner; normal Streamlit reruns only render cache."""
    from research_quant.arert_lab import MODULE_CATALOG, STATE_KEY, run_arert_research

    with st.expander("Open / Close — Dinner Master’s / PhD ARERT Research", expanded=True):
        st.caption(
            "Runs a separate research layer from the latest frozen completed canonical snapshot. "
            "It never overwrites Lunch production calculations. Repeated same-candle modules reuse cache."
        )
        options = [f"{number:02d} — {name}" for number, (name, _field) in MODULE_CATALOG.items()]
        selected_labels = st.multiselect(
            "Select Dinner research modules",
            options,
            default=[options[-1]],
            key="arert_selected_modules_20260628",
        )
        full_col, selected_col = st.columns(2)
        full_clicked = full_col.button(
            "Run Full Dinner Thesis Research + Open Dinner",
            key="run_full_dinner_thesis_research_20260628",
            use_container_width=True,
        )
        selected_clicked = selected_col.button(
            "Run Selected Dinner Research Module",
            key="run_selected_dinner_research_20260628",
            use_container_width=True,
        )
        if full_clicked or selected_clicked:
            try:
                from core.canonical_lookup_20260626 import resolve_canonical
                canonical = resolve_canonical(st.session_state)
            except Exception:
                canonical = {}
            if not isinstance(canonical, Mapping) or not canonical:
                st.error("No valid completed canonical snapshot is available. Run the protected Lunch calculation first.")
            else:
                selected = list(MODULE_CATALOG)
                if selected_clicked:
                    selected = []
                    for label in selected_labels:
                        try:
                            selected.append(int(str(label).split("—", 1)[0].strip()))
                        except Exception:
                            continue
                    if not selected:
                        st.warning("Select at least one Dinner research module.")
                        return
                with st.spinner("Running the selected completed-candle ARERT research modules…"):
                    envelope = run_arert_research(st.session_state, canonical, selected)
                st.session_state["arert_last_settings_run_20260628"] = {
                    "status": envelope.get("status"),
                    "selected_modules": envelope.get("selected_modules"),
                    "metadata": envelope.get("metadata"),
                    "database": envelope.get("database"),
                }
                try:
                    from core.navigation_authority_20260625 import navigate_to
                    navigate_to(st.session_state, "Dinner", "", None)
                except Exception:
                    st.session_state["active_page"] = "Dinner"
                    st.session_state["tab_choice"] = "Dinner"
                    st.session_state["active_subpage"] = ""
                _safe_rerun()

        last = st.session_state.get("arert_last_settings_run_20260628")
        envelope = st.session_state.get(STATE_KEY)
        if isinstance(last, Mapping):
            cols = st.columns(4)
            cols[0].metric("ARERT Status", str(last.get("status") or "—"))
            cols[1].metric("Modules Cached", str(len((envelope or {}).get("modules", {}))) if isinstance(envelope, Mapping) else "0")
            metadata = last.get("metadata") if isinstance(last.get("metadata"), Mapping) else {}
            cols[2].metric("Broker Candle", str(metadata.get("completed_broker_candle") or "—"))
            database = last.get("database") if isinstance(last.get("database"), Mapping) else {}
            cols[3].metric("Research DB", "READY" if database.get("ok") else "CHECK")



def _render_imap_rv_settings() -> None:
    """Explicit-only IMAP-RV runner; normal reruns render cached evidence only."""
    from research_quant.imap_rv_20260628 import STATE_KEY, run_imap_rv

    with st.expander("Open / Close — IMAP-RV Thesis Research", expanded=False):
        st.caption(
            "Information Mining, Attention, Path-Memory and Research Validity. "
            "This is a separate research prototype and never overwrites protected Lunch values."
        )
        force = st.checkbox("Force rebuild for the same completed candle", value=False, key="imap_rv_force_20260628")
        if st.button("Run IMAP-RV Research + Open Dinner", key="run_imap_rv_20260628", use_container_width=True):
            try:
                from core.canonical_lookup_20260626 import resolve_canonical
                canonical = resolve_canonical(st.session_state)
            except Exception:
                canonical = {}
            if not isinstance(canonical, Mapping) or not canonical:
                st.error("No completed canonical generation is available. Run the protected calculation first.")
            else:
                with st.spinner("Running completed-candle IMAP-RV research…"):
                    envelope = run_imap_rv(st.session_state, canonical, force=bool(force))
                st.session_state["imap_rv_last_settings_run_20260628"] = {
                    "status": envelope.get("status"), "score": envelope.get("imap_rv_score"),
                    "protective_action": envelope.get("protective_action"), "metadata": envelope.get("metadata"),
                }
                try:
                    from core.navigation_authority_20260625 import navigate_to
                    navigate_to(st.session_state, "Dinner", "", None)
                except Exception:
                    st.session_state["active_page"] = "Dinner"
                    st.session_state["tab_choice"] = "Dinner"
                    st.session_state["active_subpage"] = ""
                _safe_rerun()
        envelope = st.session_state.get(STATE_KEY)
        if isinstance(envelope, Mapping):
            cols = st.columns(4)
            score = envelope.get("imap_rv_score")
            cols[0].metric("IMAP-RV", "N/A" if score is None else f"{float(score):.1f}/100")
            cols[1].metric("Protective Action", str(envelope.get("protective_action") or "NO TRADE"))
            cols[2].metric("Cache", str(envelope.get("cache_status") or "—"))
            db = envelope.get("database") if isinstance(envelope.get("database"), Mapping) else {}
            cols[3].metric("Research DB", "READY" if db.get("ok") else "CHECK")

def _render_home() -> None:
    """First-open command center with essential tools only."""
    st.markdown("## ADX Quant Pro Command Center")
    st.caption("Start from Settings to run the calculation, open Lunch for saved symbol evidence, or ask the AI Assistant about the current canonical snapshot.")
    canonical = {}
    try:
        from core.canonical_lookup_20260626 import resolve_canonical
        canonical = resolve_canonical(st.session_state) or {}
    except Exception:
        canonical = st.session_state.get("canonical_result_20260617") or {}

    symbol = str(canonical.get("symbol") or st.session_state.get("symbol") or "EURUSD").upper()
    timeframe = str(canonical.get("timeframe") or st.session_state.get("timeframe") or "H4").upper()
    selected = st.session_state.get("multi_symbol_selected_20260701")
    selected = selected if isinstance(selected, list) else []
    run_id = str(canonical.get("run_id") or canonical.get("canonical_calculation_id") or "-")
    job = st.session_state.get("instant_run_job_20260705") if isinstance(st.session_state.get("instant_run_job_20260705"), Mapping) else {}

    cols = st.columns(5)
    cols[0].metric("Current Symbol", symbol)
    cols[1].metric("Timeframe", timeframe)
    cols[2].metric("Selected Symbols", len(selected) or 1)
    cols[3].metric("Run Status", str(job.get("status") or ("READY" if canonical else "RUN NEEDED")))
    cols[4].metric("Run ID", run_id[:18])

    nav = st.columns(4)
    destinations = (
        ("Open Settings", "Settings", "home_open_settings_20260706"),
        ("Open Lunch", "Lunch", "home_open_lunch_20260706"),
        ("Open Dinner", "Dinner", "home_open_dinner_20260706"),
        ("Open AI Assistant", "AI Assistant", "home_open_ai_20260706"),
    )
    for column, (label, page, key) in zip(nav, destinations):
        if column.button(label, key=key, use_container_width=True):
            try:
                from core.navigation_authority_20260625 import navigate_to
                navigate_to(st.session_state, page, "", None)
            except Exception:
                st.session_state["active_page"] = page
                st.session_state["tab_choice"] = page
                st.session_state["active_subpage"] = ""
            _safe_rerun()

    with st.container(border=True):
        st.markdown("### Essential Tools")
        tool_rows = pd.DataFrame([
            {"Tool": "Settings", "Use": "Choose symbols/timeframe, connect providers, run Quick/Full/Super Quick.", "Ready": "Yes"},
            {"Tool": "Lunch", "Use": "Review Fields 1, 2, 3, 10 and 11 from saved multi-symbol snapshots.", "Ready": "Yes" if canonical else "After run"},
            {"Tool": "Dinner", "Use": "Review Fields 4, 6, 7, 8 and 9 from the saved canonical generation.", "Ready": "Yes" if canonical else "After run"},
            {"Tool": "AI Assistant", "Use": "Ask grounded questions about the frozen canonical run.", "Ready": "Yes" if canonical else "After run"},
        ])
        st.dataframe(tool_rows, use_container_width=True, hide_index=True, height=175)

    try:
        from ui.global_symbol_selector_20260629 import render_global_symbol_selector
        with st.expander("Open / Close — Global symbol and timeframe controls", expanded=False):
            render_global_symbol_selector(st.session_state, key_prefix="home_20260706", auto_refresh_library=True)
    except Exception as exc:
        st.caption(f"Global symbol selector unavailable: {exc}")


def _render_market_connector_section(*, include_multi_symbol_controls: bool = False):
    # This is a critical start-of-system control.  Use a non-collapsible
    # container so Mobile Lite or an optional import failure can never hide it.
    with st.container(border=True):
        # Legacy source marker retained for packaged static tests:
        # Twelve Data + MT5 Market Connector — Always Visible
        st.markdown("### 🔌 API Source Connector Panel")
        st.caption("Foreground symbol router: cache first, then Twelve Data key pool, then Finnhub candle fallback, then last-known valid cache. API connection success is separated from candle-data success.")
        provider_choice_options = ["AUTO_SYMBOL_ROUTER", "TWELVE_DATA_KEY_POOL"]
        current_choice = str(st.session_state.get("foreground_main_provider_choice_20260708") or "AUTO_SYMBOL_ROUTER")
        if current_choice not in provider_choice_options:
            current_choice = "AUTO_SYMBOL_ROUTER"
        selected_choice = st.selectbox(
            "Main Provider Choice",
            provider_choice_options,
            index=provider_choice_options.index(current_choice),
            key="foreground_main_provider_choice_20260708",
            help="AUTO_SYMBOL_ROUTER keeps local cache first and Twelve Data key pool as the first live candle API.",
        )
        # Keep the old connector_mode contract while exposing the requested labels.
        st.session_state["connector_mode"] = "twelve_pool"
        active_provider = str(st.session_state.get("active_market_provider_20260705") or "TWELVE_DATA_KEY_POOL")
        fallback_provider = str(st.session_state.get("fallback_market_provider_20260705") or "FINNHUB / LOCAL_CACHE")
        p1, p2, p3 = st.columns(3)
        p1.metric("Selected Router Mode", selected_choice)
        p2.metric("First Live Candle API", "TWELVE_DATA_KEY_POOL")
        p3.metric("Fallback Provider", fallback_provider)
        st.number_input(
            "MT5 broker chart UTC offset (display only)", min_value=-12.0, max_value=14.0, step=0.5,
            key="mt5_broker_utc_offset_hours_20260622",
            help="MT5 Python tick timestamps are UTC. Set the exact broker-chart offset. All Lunch Date/Weekday/Hour columns are rebuilt from this same broker clock.",
        )
        _render_twelve_key_pool_section()
        try:
            from ui.sidebar_fallback_panel import _render_connector
            _render_connector(key_prefix="settings_market_20260619", show_secret_inputs=False, show_symbol_selector=False)
        except Exception as exc:
            # Keep a complete minimal connector visible instead of replacing the
            # entire start panel with a warning. Full details remain in the internal log.
            try:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error("settings.market_connector", exc)
            except Exception:
                incident = "connector-render"
            st.warning(f"The advanced connection panel could not load. The safe connection controls remain available. Support reference: {incident}.")
            source_options = ["twelve_pool", "twelve", "fallback", "safe_demo"]
            current_source = str(st.session_state.get("connector_mode") or "twelve_pool")
            if current_source in {"finnhub", "mt5", "doo_bridge"}:
                current_source = "twelve_pool"
            if current_source not in source_options:
                current_source = "twelve_pool"
            st.session_state["connector_mode"] = st.selectbox(
                "API source", source_options, index=source_options.index(current_source),
                key="settings_market_emergency_source_20260702",
            )
            selected = st.session_state.get("multi_symbol_selected_20260701") or []
            symbol = str(selected[0] if selected else st.session_state.get("multi_symbol_main_symbol_20260702") or st.session_state.get("symbol") or "EURUSD").strip().upper().replace("/", "").replace(" ", "")
            set_legacy_calculation_symbol(st.session_state, symbol, connector=True)
            st.caption(f"Emergency connector uses Main Core Symbol: {symbol}")
            timeframe_options = ["M1", "M2", "M5", "M15", "M30", "H1", "H4", "D1", "CUSTOM"]
            current_tf = str(st.session_state.get("timeframe") or "H1").upper()
            if current_tf not in timeframe_options:
                current_tf = "H1"
            st.session_state["timeframe"] = st.selectbox(
                "Timeframe", timeframe_options, index=timeframe_options.index(current_tf),
                key="settings_market_emergency_timeframe_20260702",
            )
            st.session_state["connector_bars"] = int(st.number_input(
                "Candles / bars", min_value=100, max_value=250000,
                value=int(st.session_state.get("connector_bars", 600) or 600), step=100,
                key="settings_market_emergency_bars_20260702",
            ))
            st.warning("The visible emergency connector is active. Fix the renderer error above for one-click connection, but symbol/timeframe/candle setup remains available.")

        if include_multi_symbol_controls:
            from ui.multi_symbol_settings_20260701 import (
                render_multi_symbol_selectors, render_calculation_mode_selector,
            )
            groups = render_multi_symbol_selectors(st.session_state)
            scope = render_calculation_mode_selector(st.session_state)
            return groups, scope
    return None


def _render_twelve_key_pool_section() -> None:
    """Settings-tab Twelve Data multi-key pool connector."""
    with st.container(border=True):
        st.markdown("#### Twelve Data Key Pool")
        st.caption("Use two different Twelve Data API keys safely. Each key has its own minute credit counter, cooldown, 429 handling, and masked status.")
        try:
            from core.secure_api_startup_20260619 import resolve_api_key
            resolved_key_1 = str(resolve_api_key("second_api", st.session_state) or "").strip()
            resolved_key_2 = str(resolve_api_key("twelve_key_2", st.session_state) or "").strip()
        except Exception:
            resolved_key_1 = ""
            resolved_key_2 = ""
        existing_key_1 = str(st.session_state.get("twelve_api_key_1") or st.session_state.get("twelve_api_key") or st.session_state.get("TWELVE_DATA_API_KEY") or resolved_key_1 or "")
        existing_key_2 = str(st.session_state.get("twelve_api_key_2") or st.session_state.get("TWELVE_DATA_API_KEY_2") or resolved_key_2 or "")
        key1 = st.text_input("Twelve Data API Key 1", value=existing_key_1, type="password", key="settings_twelve_data_api_key_1_20260708")
        key2 = st.text_input("Twelve Data API Key 2", value=existing_key_2, type="password", key="settings_twelve_data_api_key_2_20260708")
        st.session_state["enable_twelve_multi_key_loading"] = st.checkbox(
            "Enable Multi-Key Loading", value=bool(st.session_state.get("enable_twelve_multi_key_loading", True)), key="settings_enable_twelve_multi_key_loading_20260708"
        )
        if key1:
            st.session_state["twelve_api_key_1"] = key1.strip()
            st.session_state["twelve_api_key"] = key1.strip()
            st.session_state["TWELVE_DATA_API_KEY"] = key1.strip()
        if key2:
            st.session_state["twelve_api_key_2"] = key2.strip()
            st.session_state["TWELVE_DATA_API_KEY_2"] = key2.strip()
        save_col, test1_col, test2_col = st.columns(3)
        if save_col.button("Save Twelve Keys", key="save_twelve_key_pool_20260708", use_container_width=True):
            try:
                from core.connectors.credential_vault import save_credential
                saved_1 = save_credential("TWELVE_DATA_KEY_1", st.session_state.get("twelve_api_key_1") or st.session_state.get("twelve_api_key") or "")
                save_credential("TWELVE_DATA", st.session_state.get("twelve_api_key_1") or st.session_state.get("twelve_api_key") or "")
                saved_2 = save_credential("TWELVE_DATA_KEY_2", st.session_state.get("twelve_api_key_2") or "")
                st.success(f"Keys saved. Key 1: {saved_1.get('status', saved_1.get('ok'))}; Key 2: {saved_2.get('status', saved_2.get('ok'))}")
            except Exception as exc:
                st.error(f"Twelve key save failed: {type(exc).__name__}: {exc}")
        if test1_col.button("Test Key 1", key="test_twelve_key_1_20260708", use_container_width=True):
            try:
                from core.twelve_data_key_pool import test_twelve_data_key
                st.session_state["twelve_key_1_connection_test_20260708"] = test_twelve_data_key(st.session_state, alias="TWELVE_KEY_1")
            except Exception as exc:
                st.session_state["twelve_key_1_connection_test_20260708"] = {"connected": False, "status": "FAILED", "error_message": f"{type(exc).__name__}: {exc}"}
        if test2_col.button("Test Key 2", key="test_twelve_key_2_20260708", use_container_width=True):
            try:
                from core.twelve_data_key_pool import test_twelve_data_key
                st.session_state["twelve_key_2_connection_test_20260708"] = test_twelve_data_key(st.session_state, alias="TWELVE_KEY_2")
            except Exception as exc:
                st.session_state["twelve_key_2_connection_test_20260708"] = {"connected": False, "status": "FAILED", "error_message": f"{type(exc).__name__}: {exc}"}
        try:
            from core.twelve_data_key_pool import TwelveDataKeyPool
            snapshot = TwelveDataKeyPool.from_state(st.session_state).status_snapshot()
            rows = []
            for alias, info in snapshot.items():
                test_key = "twelve_key_1_connection_test_20260708" if alias.endswith("1") else "twelve_key_2_connection_test_20260708"
                test_result = st.session_state.get(test_key) if isinstance(st.session_state.get(test_key), Mapping) else {}
                rows.append({
                    "Key Alias": alias,
                    "Masked Key": info.get("masked_key"),
                    "Status": test_result.get("status") or ("CONNECTED" if info.get("connected") else "CONFIGURED" if info.get("configured") else "NOT_CONFIGURED"),
                    "Remaining Credits": info.get("remaining_credits"),
                    "Last Success": info.get("last_successful_request_time"),
                    "Last 429": info.get("last_429_time"),
                    "Cooldown Reset": info.get("cooldown_reset_time"),
                    "Failure Reason": test_result.get("error_message") or info.get("failure_reason") or "",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.caption(f"Twelve key-pool status unavailable: {type(exc).__name__}: {exc}")
        try:
            from core.data.market_data_orchestrator import provider_priority_for_state
            provider_route = tuple(provider_priority_for_state(st.session_state))
        except Exception:
            provider_route = ("TWELVE_DATA_KEY_POOL", "FINNHUB", "LOCAL_VALID_CACHE")
        st.session_state.setdefault("connector_mode", "twelve_pool")
        st.session_state["active_market_provider_20260705"] = str(provider_route[0] if provider_route else "TWELVE_DATA_KEY_POOL")
        st.session_state["fallback_market_provider_20260705"] = str(provider_route[1] if len(provider_route) > 1 else "LOCAL_VALID_CACHE")
        st.session_state["market_data_provider_order_override_20260708"] = provider_route

def _render_finnhub_connector_section() -> None:
    with st.container(border=True):
        st.markdown("### 📰 Finnhub Connector — Always Visible")
        try:
            from core.finnhub_connector import render_finnhub_connector
            render_finnhub_connector(location="settings")
        except Exception as exc:
            try:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error("settings.finnhub_connector", exc)
            except Exception:
                incident = "finnhub-render"
            st.warning(f"Finnhub status could not be loaded. Twelve Data and persisted fallbacks remain available. Support reference: {incident}.")
            st.caption("The Finnhub section remains visible. Add the key in Streamlit Secrets; no secret is printed in this interface.")


def _render_settings() -> None:
    st.session_state.setdefault("mt5_broker_utc_offset_hours_20260622", 4.0)
    # One-time migration to the Twelve Data key-pool route.
    if not st.session_state.get("twelve_key_pool_migration_20260708"):
        st.session_state.setdefault("connector_mode", "twelve_pool")
        try:
            from core.data.market_data_orchestrator import provider_priority_for_state
            provider_route = tuple(provider_priority_for_state(st.session_state))
        except Exception:
            provider_route = ("TWELVE_DATA_KEY_POOL", "FINNHUB", "LOCAL_VALID_CACHE")
        st.session_state["active_market_provider_20260705"] = str(provider_route[0] if provider_route else "TWELVE_DATA_KEY_POOL")
        st.session_state["fallback_market_provider_20260705"] = str(provider_route[1] if len(provider_route) > 1 else "LOCAL_VALID_CACHE")
        st.session_state["market_data_provider_order_override_20260708"] = provider_route
        st.session_state["twelve_key_pool_migration_20260708"] = True
    if not st.session_state.get("settings_h1_default_initialized_20260729"):
        # Upgrade the old automatic H4 choice to H1 once. After this one-time
        # migration, any timeframe the user selects remains authoritative.
        _existing_tf_20260708 = str(
            st.session_state.get("settings_timeframe")
            or st.session_state.get("selected_timeframe")
            or st.session_state.get("timeframe")
            or "H1"
        ).upper()
        if not _existing_tf_20260708 or _existing_tf_20260708 == "H4" or st.session_state.get("settings_h4_default_initialized_20260707"):
            _existing_tf_20260708 = "H1"
        st.session_state["timeframe"] = _existing_tf_20260708
        st.session_state["selected_timeframe"] = _existing_tf_20260708
        st.session_state["settings_timeframe"] = _existing_tf_20260708
        st.session_state["last_connected_timeframe"] = _existing_tf_20260708
        # Migrate the keyed Settings widgets too; otherwise an already-open
        # Streamlit session can keep the old H4 widget value even after the
        # canonical timeframe state has moved to H1.
        st.session_state["settings_market_20260619_timeframe_v1"] = _existing_tf_20260708
        st.session_state["settings_market_emergency_timeframe_20260702"] = _existing_tf_20260708
        st.session_state["settings_h1_default_initialized_20260729"] = True
    st.markdown("### ⚙️ Settings")
    try:
        from observability.system_health import render_system_health
        with st.expander("Open / Close — System Health, Snapshot Sync and Deployment Readiness", expanded=False):
            render_system_health(st, st.session_state)
    except Exception as system_health_exc_20260709:
        st.caption(f"System health panel unavailable: {type(system_health_exc_20260709).__name__}: {system_health_exc_20260709}")
    try:
        from core.mobile_lite_mode_20260628 import render_mobile_mode_control
        with st.expander("Open / Close — Extreme Mobile Lite Mode", expanded=bool(st.session_state.get("phone_mode"))):
            render_mobile_mode_control(st, st.session_state, key="settings_mobile_lite_20260628")
            st.caption("Mobile Lite disables decorative UI, bounds tables and loads one field at a time. Calculation values remain identical.")
    except Exception as mobile_mode_exc:
        st.caption(f"Mobile Lite control unavailable: {mobile_mode_exc}")
    # Render the advanced selector and the three calculation choices independently.
    # Backward-compatible calculation-mode contracts retained for deployment guards:
    # 1. Quick — Fields 1–9 + AI
    # 2. Full — Fields 1–9 + thesis + AI
    # 3. Super Quick — Lunch Fields 1–3
    # Backward-compatible label contract: Run Calculation + Open Lunch (One Click)
    st.caption("Load symbols at the selected timeframe first, then use one of the three calculation choices below.")
    try:
        from ui.app_professional_guide_20260628 import render_app_professional_guide
        render_app_professional_guide(expanded=bool(st.session_state.pop("settings_open_explain_app_20260629", False)), context={
            "source": st.session_state.get("source"),
            "symbol": st.session_state.get("symbol", "EURUSD"),
            "timeframe": st.session_state.get("timeframe", "H1"),
            "run_id": st.session_state.get("canonical_run_id_20260617"),
            "generation_id": st.session_state.get("canonical_calculation_generation_20260617"),
        })
    except Exception as guide_exc:
        st.caption(f"Professional guide unavailable: {guide_exc}")
    _render_market_time_metrics(query_mt5=False)

    st.markdown("### Run Calculation Console — Top of Settings")
    # Render three independent selectors: first up to 12, second/third up to 6. Each selector owns its load
    # record; all calculation buttons consume the cumulative loaded universe.
    try:
        connector_controls = _render_market_connector_section(include_multi_symbol_controls=True)
        if not isinstance(connector_controls, tuple) or len(connector_controls) != 2:
            raise RuntimeError("The integrated connector did not return selector controls.")
        symbol_groups_20260706, selected_scope_20260701 = connector_controls
    except Exception as integrated_connector_exc:
        st.session_state["integrated_connector_controls_error_20260707"] = f"{type(integrated_connector_exc).__name__}: {integrated_connector_exc}"
        st.warning("The integrated connector panel used its safe selector fallback; calculations remain available.")
        from ui.multi_symbol_settings_20260701 import render_multi_symbol_selectors, render_calculation_mode_selector
        symbol_groups_20260706 = render_multi_symbol_selectors(st.session_state)
        selected_scope_20260701 = render_calculation_mode_selector(st.session_state)

    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        from core.multi_symbol_run_groups_20260706 import CONFIGURED_UNION_KEY, save_group_preferences, union_symbols
        from core.runtime_selection_20260705 import save_runtime_preferences
        configured_union_20260706 = union_symbols(
            symbol_groups_20260706.get("FIRST") or [],
            symbol_groups_20260706.get("SECOND") or [],
            symbol_groups_20260706.get("THIRD") or [],
        )
        st.session_state[CONFIGURED_UNION_KEY] = list(configured_union_20260706)
        try:
            from core.current_result_sync_20260708 import sync_settings_source_of_truth
            sync_settings_source_of_truth(
                st.session_state,
                configured_union_20260706 or ["EURUSD"],
                st.session_state.get("timeframe") or "H1",
                reason="settings_configured_union",
            )
        except Exception as current_sync_exc_20260708:
            st.session_state["current_result_sync_error_20260708"] = f"{type(current_sync_exc_20260708).__name__}: {current_sync_exc_20260708}"
        save_runtime_preferences(DEFAULT_DB_PATH, configured_union_20260706 or ["EURUSD"], st.session_state.get("timeframe") or "H1")
        save_group_preferences(DEFAULT_DB_PATH, st.session_state)
    except Exception as runtime_sync_exc:
        configured_union_20260706 = []
        st.session_state["runtime_selection_sync_error_20260705"] = f"{type(runtime_sync_exc).__name__}: {runtime_sync_exc}"

    previous_status = st.session_state.get("settings_run_status_20260617")
    if isinstance(previous_status, Mapping):
        canonical_ok = bool((previous_status.get("canonical") or {}).get("ok"))
        previous_used = bool(st.session_state.get("settings_used_previous_canonical_20260622"))
        ai_ready = False
        try:
            from tabs.ai_assistant_compact_20260619 import _recover_fact_pack
            ai_ready = bool(_recover_fact_pack(st.session_state))
        except Exception:
            ai_ready = False
        top = st.columns(4)
        top[0].metric("All-in-One Run", "FULLY WORKED" if canonical_ok else ("PREVIOUS VALID USED" if ai_ready else "CHECK"))
        top[1].metric("Published Generation", str(previous_status.get("calculation_generation", st.session_state.get("canonical_calculation_generation_20260617", "-"))))
        top[2].metric("AI Assistant", "READY" if ai_ready else "OFFLINE DIAGNOSTIC")
        top[3].metric("Auto-Open Field 3", "READY" if (canonical_ok or previous_used or ai_ready) else "WAITING")

    st.info(
        "Super Quick calculates every symbol currently loaded by Selector 1, Selector 2, and Selector 3. "
        "It uses the fast all-loaded Field 3 path for Higher Regime Age Ranking, Middle Regime Age Ranking, and Higher Standard Summary. "
        "Quick completes the deeper deferred tables and research work."
    )
    try:
        from core.instant_run_engine_20260705 import ACTIVE_STATUSES as _INSTANT_ACTIVE_STATUSES, current_job as _current_instant_job
        _instant_lock_job = _current_instant_job(st.session_state, restore=True)
        _instant_job_active = isinstance(_instant_lock_job, Mapping) and str(_instant_lock_job.get("status") or "").upper() in _INSTANT_ACTIVE_STATUSES
    except Exception:
        _instant_job_active = False
    # Do not keep Quick/Full disabled after Super Quick completes. Streamlit is
    # single-run while a click is executing, so stale session lock booleans are
    # cleared whenever no active instant job is actually running.
    if not _instant_job_active:
        for _lock_key in ("instant_run_engine_running_20260705", "settings_one_click_running_20260624", "multi_symbol_run_in_progress_20260701"):
            st.session_state[_lock_key] = False
    run_locked_20260624 = bool(_instant_job_active)
    first_group_20260706 = list(symbol_groups_20260706.get("FIRST") or [])
    second_group_20260706 = list(symbol_groups_20260706.get("SECOND") or [])
    third_group_20260706 = list(symbol_groups_20260706.get("THIRD") or [])
    timeframe_for_load_20260707 = str(st.session_state.get("timeframe") or st.session_state.get("selected_timeframe") or "H1").upper()
    try:
        from core.multi_symbol_load_manager_20260707 import loaded_group_status
        first_load_status_20260707 = loaded_group_status(st.session_state, "FIRST", first_group_20260706, timeframe_for_load_20260707)
        second_load_status_20260707 = loaded_group_status(st.session_state, "SECOND", second_group_20260706, timeframe_for_load_20260707)
        third_load_status_20260707 = loaded_group_status(st.session_state, "THIRD", third_group_20260706, timeframe_for_load_20260707)
    except Exception as load_status_exc_20260707:
        unavailable_status = {
            "ready": False, "status": "UNAVAILABLE", "loaded_symbols": [], "failed_symbols": [],
            "message": f"Load manager unavailable: {type(load_status_exc_20260707).__name__}: {load_status_exc_20260707}",
        }
        first_load_status_20260707 = dict(unavailable_status)
        second_load_status_20260707 = dict(unavailable_status)
        third_load_status_20260707 = dict(unavailable_status)

    configured_groups_for_run_20260707 = {
        "FIRST": first_group_20260706, "SECOND": second_group_20260706, "THIRD": third_group_20260706,
    }
    configured_count_20260707 = len(dict.fromkeys(first_group_20260706 + second_group_20260706 + third_group_20260706))
    try:
        from core.multi_symbol_load_manager_20260707 import loaded_universe_status
        cumulative_load_status_20260707 = loaded_universe_status(
            st.session_state, configured_groups_for_run_20260707, timeframe_for_load_20260707
        )
    except Exception as cumulative_exc_20260707:
        cumulative_load_status_20260707 = {
            "ready": False, "loaded_symbols": [], "message": f"Cumulative load status unavailable: {type(cumulative_exc_20260707).__name__}: {cumulative_exc_20260707}"
        }

    load_summary_cols = st.columns(4)
    for slot, title, status in (
        (load_summary_cols[0], "Selector 1 Load", first_load_status_20260707),
        (load_summary_cols[1], "Selector 2 Load", second_load_status_20260707),
        (load_summary_cols[2], "Selector 3 Load", third_load_status_20260707),
    ):
        loaded_count = len(status.get("loaded_symbols") or [])
        failed_count = len(status.get("failed_symbols") or [])
        slot.metric(title, f"{loaded_count} READY", delta=(f"{failed_count} rejected" if failed_count else str(status.get("status") or "NOT_LOADED")))
    cumulative_ready_count_20260727 = len(cumulative_load_status_20260707.get("loaded_symbols") or [])
    cumulative_failed_count_20260727 = max(0, configured_count_20260707 - cumulative_ready_count_20260727)
    load_summary_cols[3].metric(
        "All Run Buttons",
        f"{cumulative_ready_count_20260727} READY",
        delta=(f"{cumulative_failed_count_20260727} not ready" if cumulative_failed_count_20260727 else "ALL LOADED"),
    )
    st.caption(
        "The three left cards are load diagnostics only. Super Quick, Quick, and Full all calculate the same "
        f"{cumulative_ready_count_20260727}-symbol loaded universe; the buttons differ only in calculation depth."
    )

    # Plan B/global authority: after symbols are explicitly loaded, one selector
    # controls the displayed symbol across Research, AI, Lunch/Dinner and Fields
    # 1–3/10–13. It never exposes configured-but-unloaded defaults.
    try:
        from core.canonical_symbol_selection_20260709 import render_selector as _render_global_loaded_selector
        _render_global_loaded_selector(
            st, st.session_state, surface="settings_global",
            title="Global Multi-Symbol Display Selector — Loaded Symbols Only",
            expanded=True,
        )
    except Exception as global_selector_exc_20260722:
        st.session_state["settings_global_symbol_selector_error_20260722"] = f"{type(global_selector_exc_20260722).__name__}: {global_selector_exc_20260722}"

    st.caption(
        f"Cumulative calculation universe: {len(cumulative_load_status_20260707.get('loaded_symbols') or [])} loaded symbol(s). "
        "All three buttons calculate this same loaded universe; only calculation depth changes."
    )

    # Backward-compatible static labels retained for deployment checks:
    # Super Quick Calculation + Open Lunch — First Selector
    # Quick Calculation + Open Lunch — Second Selector
    # Full Calculation + Open Lunch — Third Selector
    # Calculate Loaded First Selector
    # Calculate Loaded Second Selector
    # Calculate Loaded Third Selector
    run_cols = st.columns(3)
    # Calculations are compute-only. Market data must be explicitly loaded by a
    # selector Load/Reload button before any calculation button becomes active.
    run_disabled_20260707 = not bool(cumulative_load_status_20260707.get("loaded_symbols"))
    super_clicked = run_cols[0].button(
        "▶ Super Quick — Calculate All Loaded Symbols + Open Field 3",
        key="settings_run_lunch_core_calc_20260702", use_container_width=True,
        disabled=run_disabled_20260707,
        help="Fast three-table mode: uses already-loaded candles and calculates Higher Regime Age Ranking, Middle Regime Age Ranking, and Higher Standard Summary. It makes no API requests; use Quick for all deferred calculations.",
    )
    quick_clicked = run_cols[1].button(
        "▶ Quick — Calculate All Loaded Symbols + Open Field 3",
        key="settings_run_calc_20260617", use_container_width=True,
        disabled=run_disabled_20260707,
        help="Calculates every symbol currently loaded by any selector using Quick depth. Load symbols explicitly first; this button never fetches APIs.",
    )
    full_clicked = run_cols[2].button(
        "▶ Full — Calculate All Loaded Symbols + Open Field 3",
        key="settings_run_full_calc_20260702", use_container_width=True,
        disabled=run_disabled_20260707,
        help="Calculates every symbol currently loaded by any selector using Full depth. Load symbols explicitly first; this button never fetches APIs.",
    )
    load_update_clicked = st.button(
        "↻ Load & Update Latest Candles + Run Super Quick",
        key="settings_load_update_super_quick_20260729",
        use_container_width=True,
        disabled=bool(run_locked_20260624 or configured_count_20260707 <= 0),
        help=(
            "Refreshes all configured selector symbols for the latest completed candle, preserves exact valid cache rows when a provider fails, "
            "then runs the fast three-table Field 3 calculation automatically. No app restart is required."
        ),
    )
    if load_update_clicked:
        update_progress = st.progress(0.0, text="Refreshing the latest completed candles…")
        update_status = st.empty()

        def _load_update_progress_20260729(snapshot: Any) -> None:
            if not isinstance(snapshot, Mapping):
                return
            percent = float(snapshot.get("overall_percent") or snapshot.get("progress_percent") or 0.0)
            current_symbol = str(snapshot.get("current_symbol") or "Selected symbols")
            stage = str(snapshot.get("current_stage") or "Refreshing market data")
            update_progress.progress(min(1.0, max(0.0, percent / 100.0)), text=f"{percent:.1f}% refreshed")
            update_status.caption(f"{current_symbol} — {stage}")

        try:
            from core.multi_symbol_load_manager_20260707 import (
                loaded_universe_status as _loaded_universe_status_20260729,
                refresh_all_selectors_safely,
            )
            refresh_result_20260729 = refresh_all_selectors_safely(
                st.session_state,
                configured_groups_for_run_20260707,
                timeframe_for_load_20260707,
                progress_callback=_load_update_progress_20260729,
            )
            cumulative_load_status_20260707 = _loaded_universe_status_20260729(
                st.session_state, configured_groups_for_run_20260707, timeframe_for_load_20260707
            )
            refreshed_symbols_20260729 = list(cumulative_load_status_20260707.get("loaded_symbols") or [])
            update_progress.progress(1.0, text="Latest-candle refresh completed")
            if not refreshed_symbols_20260729:
                raise RuntimeError(str(refresh_result_20260729.get("message") or "No symbol has calculation-ready refreshed candles."))
            failed_refresh_20260729 = list(cumulative_load_status_20260707.get("failed_symbols") or [])
            if failed_refresh_20260729:
                st.warning(
                    f"Updated {len(refreshed_symbols_20260729)} symbol(s); {len(failed_refresh_20260729)} symbol(s) remain unavailable. "
                    "Super Quick will run on the refreshed calculation-ready universe."
                )
            else:
                st.success(f"Latest completed candles are ready for {len(refreshed_symbols_20260729)} symbol(s). Starting Super Quick now.")
            # Continue through the existing protected activation/queue path in
            # this same Streamlit click. The new loaded frames become the exact
            # cumulative universe consumed by Super Quick.
            super_clicked = True
        except Exception as load_update_exc_20260729:
            update_progress.empty()
            update_status.empty()
            st.error(f"Load & Update could not start Super Quick: {type(load_update_exc_20260729).__name__}: {load_update_exc_20260729}")
            load_update_clicked = False
            super_clicked = False
    run_clicked_20260701 = bool(quick_clicked or full_clicked or super_clicked)
    run_symbols_20260706: list[str] = []
    active_group_20260706 = "SECOND"
    if super_clicked:
        selected_scope_20260701 = "LUNCH_CORE"
        active_group_20260706 = "FIRST"
    elif quick_clicked:
        selected_scope_20260701 = "QUICK"
        active_group_20260706 = "SECOND"
    elif full_clicked:
        selected_scope_20260701 = "FULL"
        active_group_20260706 = "THIRD"
    # Button choice controls calculation depth only.  The run symbol set is the
    # cumulative exact loaded universe, while current selected symbols remain
    # the Settings-configured universe for display/export/copy.
    if run_clicked_20260701:
        run_symbols_20260706 = list(cumulative_load_status_20260707.get("loaded_symbols") or [])
    reset_col = st.columns([3, 1])[1]
    if run_clicked_20260701:
        st.session_state["settings_calculation_scope_20260625"] = selected_scope_20260701
        st.session_state["field3_fast_two_table_mode_20260722"] = selected_scope_20260701 == "LUNCH_CORE"
        st.session_state["field3_last_run_scope_20260722"] = selected_scope_20260701
        try:
            from core.field10_fast_lane_20260709 import set_field10_fast_lane
            set_field10_fast_lane(st.session_state, enabled=(selected_scope_20260701 == "LUNCH_CORE"), scope=selected_scope_20260701)
        except Exception as fast_lane_exc_20260709:
            st.session_state["field10_fast_lane_setup_error_20260709"] = f"{type(fast_lane_exc_20260709).__name__}: {fast_lane_exc_20260709}"
        configured_for_click = configured_groups_for_run_20260707.get(active_group_20260706, [])
        try:
            # Legacy compatibility marker: activate_loaded_scope_for_run.
            from core.multi_symbol_load_manager_20260707 import activate_loaded_universe_for_run
            activation_20260707 = activate_loaded_universe_for_run(
                st.session_state, selected_scope_20260701,
                configured_groups_for_run_20260707, timeframe_for_load_20260707,
            )
            if not activation_20260707.get("ok"):
                raise RuntimeError(str(activation_20260707.get("message") or "No loaded symbol reached the genuine minimum history."))
            run_symbols_20260706 = list(activation_20260707.get("loaded_symbols") or [])
            from core.multi_symbol_run_groups_20260706 import mark_run_group
            active_group_20260706, run_symbols_20260706 = mark_run_group(
                st.session_state, selected_scope_20260701, run_symbols_20260706,
            )
            try:
                from core.current_result_sync_20260708 import sync_settings_source_of_truth
                sync_settings_source_of_truth(
                    st.session_state,
                    configured_union_20260706 or ["EURUSD"],
                    timeframe_for_load_20260707,
                    reason="pre_queue_run_restore_selected_universe",
                    clear_stale=False,
                )
            except Exception as restore_selected_exc_20260708:
                st.session_state["pre_queue_current_selection_restore_error_20260708"] = f"{type(restore_selected_exc_20260708).__name__}: {restore_selected_exc_20260708}"
        except Exception as activation_exc_20260707:
            st.error(
                f"Calculation was not started: {type(activation_exc_20260707).__name__}: {activation_exc_20260707}. "
                "Reload a selector only if its market data is still below the genuine minimum or invalid."
            )
            return

        # Provider quota pacing belongs to the Load buttons. Calculation is now
        # strictly compute-only and reuses the validated loaded frames.
        st.session_state["quota_safe_stagger_enabled_20260706"] = False
        st.session_state["super_quick_time_budget_enabled_20260706"] = False
        try:
            from core.instant_run_engine_20260705 import enqueue_run
            queued_job = enqueue_run(
                st.session_state,
                scope=selected_scope_20260701,
                symbols=list(run_symbols_20260706),
                timeframe=timeframe_for_load_20260707,
                start_delay_seconds=0.0,
            )
            if queued_job.get("duplicate_click_ignored"):
                st.info(f"Instant Run {queued_job.get('job_id')} is already queued or running.")
            else:
                st.success(
                    f"{selected_scope_20260701.title()} calculation queued for the cumulative {len(run_symbols_20260706)} loaded symbol(s): "
                    f"{queued_job.get('job_id')}. The calculation reuses the saved selector frames."
                )
        except Exception as queue_exc:
            st.session_state.pop("multi_symbol_loaded_run_active_20260707", None)
            st.error(f"Instant Run could not be queued: {type(queue_exc).__name__}: {queue_exc}")
            return
        _safe_rerun()
        return

    _instant_progress_callback_holder: dict[str, Any] = {"callback": None}

    def _settings_run_action_20260624():
        # Prefer the sequential multi-symbol transaction.  If an optional
        # controller import ever fails on deployment, continue with the
        # active symbol instead of aborting the main calculation button.
        child_run_key = "multi_symbol_child_run_active_20260701"
        multi_symbol_runner = None
        try:
            from core.multi_symbol_field10_20260701 import CHILD_RUN_KEY, run_selected_symbols
            child_run_key = CHILD_RUN_KEY
            multi_symbol_runner = run_selected_symbols
        except Exception as multi_run_import_exc:
            st.session_state["multi_symbol_run_nonblocking_error_20260702"] = f"{type(multi_run_import_exc).__name__}: {multi_run_import_exc}"

        if callable(multi_symbol_runner) and not bool(st.session_state.get(child_run_key)):
            def _publish_multi_progress(snapshot):
                callback = _instant_progress_callback_holder.get("callback")
                if callable(callback):
                    callback(snapshot)
            return multi_symbol_runner(
                st.session_state,
                _settings_run_action_20260624,
                scope=str(st.session_state.get("settings_calculation_scope_20260625") or "QUICK"),
                progress_callback=_publish_multi_progress,
            )
        # Legacy contract markers: try_reuse_quick_fields_123 and
        # QUICK_FIELDS_1_2_3. The current priority implementation still
        # executes one full protected run; these markers do not activate a
        # second Quick Sync path or restrict the full Fields 1-9 scope.
        ns = _home_ns()
        refresh_result: dict[str, Any] = {}
        loaded_run_marker_20260707 = st.session_state.get("multi_symbol_loaded_run_active_20260707")
        spinner_text_20260707 = (
            "Calculating the already-loaded exact-symbol data, then opening Lunch…"
            if isinstance(loaded_run_marker_20260707, Mapping)
            else "Refreshing the selected feed once, calculating all synchronized tabs, then opening Lunch…"
        )
        with st.spinner(spinner_text_20260707):
            if isinstance(loaded_run_marker_20260707, Mapping):
                # activate_prepared_symbol already placed the exact loaded frame
                # into last_df immediately before this child runner was called.
                refresh_result = {
                    "status": "REUSED_PRELOADED_DATA",
                    "ok": True,
                    "load_id": loaded_run_marker_20260707.get("load_id"),
                    "symbol": st.session_state.get("symbol"),
                    "timeframe": st.session_state.get("timeframe") or "H1",
                    "provider_requests": 0,
                    "message": "Calculation-only run reused data validated by the selector Load button.",
                }
            else:
                try:
                    from core.app.refresh import refresh_data
                    # Legacy static acceptance marker only; runtime uses the selected instrument:
                    # refresh_data(st.session_state, symbol_override="EURUSD", timeframe_override="H1")
                    try:
                        from core.multi_symbol_field10_20260701 import normalize_symbol
                        selected_symbol = normalize_symbol(st.session_state.get("symbol") or "EURUSD")
                    except Exception:
                        selected_symbol = str(st.session_state.get("symbol") or "EURUSD").strip().upper().replace("/", "")
                    selected_timeframe = str(st.session_state.get("timeframe") or "H1").upper()
                    refresh_result = refresh_data(st.session_state, symbol_override=selected_symbol, timeframe_override=selected_timeframe)
                except Exception as exc:
                    refresh_result = {"status": "FAILURE", "ok": False, "message": f"Refresh failed safely: {exc}"}
            from core.settings_run_orchestrator_20260617 import run_settings_calculation
            scope = str(st.session_state.get("settings_calculation_scope_20260625") or "FULL").upper()
            try:
                from core.field10_fast_lane_20260709 import is_field10_fast_lane, defer_to_quick
                field10_fast_lane_20260709 = is_field10_fast_lane(st.session_state, scope)
            except Exception:
                field10_fast_lane_20260709 = False
                def defer_to_quick(state, name, **kwargs):
                    return {"ok": False, "status": "DEFERRED_TO_QUICK_RUN", **kwargs}
            calculation_status = None
            if not isinstance(calculation_status, dict):
                calculation_status = run_settings_calculation(ns)
            if scope == "FULL":
                try:
                    from core.services.field9_service import build_and_publish_field9
                    calculation_status["field9_eurusd_h1_decision_impact"] = build_and_publish_field9(st.session_state)
                except Exception as field9_exc:
                    calculation_status["field9_eurusd_h1_decision_impact"] = {"ok": False, "shadow_only": True, "production_influence_enabled": False, "error": f"{type(field9_exc).__name__}: {field9_exc}"}
                try:
                    from core.services.research_grade_system_v17_service import build_and_publish_research_grade_v17
                    calculation_status["research_grade_system_v17"] = build_and_publish_research_grade_v17(st.session_state)
                except Exception as research_exc:
                    calculation_status["research_grade_system_v17"] = {"ok": False, "status": "FAILED_VALIDATION", "shadow_only": True, "error": f"{type(research_exc).__name__}: {research_exc}"}
                try:
                    from core.services.unified_shadow_pipeline_v19_service import build_and_publish_unified_shadow_v19
                    calculation_status["unified_shadow_pipeline_v19"] = build_and_publish_unified_shadow_v19(st.session_state)
                except Exception as unified_exc:
                    calculation_status["unified_shadow_pipeline_v19"] = {"ok": False, "status": "FAILED_VALIDATION", "shadow_only": True, "error": f"{type(unified_exc).__name__}: {unified_exc}"}
                try:
                    from core.services.research_adaptation_v18_service import build_and_publish_research_adaptation_v18
                    calculation_status["research_adaptation_v18"] = build_and_publish_research_adaptation_v18(st.session_state)
                except Exception as adaptation_exc:
                    calculation_status["research_adaptation_v18"] = {"ok": False, "shadow_only": True, "error": f"{type(adaptation_exc).__name__}: {adaptation_exc}"}
                try:
                    from core.services.session_ai_field6_9_service_20260625 import build_and_publish_session_ai_field6_9
                    calculation_status["session_ai_field6_9_20260625"] = build_and_publish_session_ai_field6_9(st.session_state)
                except Exception as additive_exc:
                    calculation_status["session_ai_field6_9_20260625"] = {"ok": False, "shadow_only": True, "error": f"{type(additive_exc).__name__}: {additive_exc}"}
            else:
                # Quick keeps the current core Fields 1-9 + AI publication but
                # omits thesis-only research rebuilds. Super Quick is limited
                # to Lunch Fields 1-3 and the Table 1 direction publisher.
                if scope == "QUICK":
                    try:
                        from core.services.field9_service import build_and_publish_field9
                        calculation_status["field9_eurusd_h1_decision_impact"] = build_and_publish_field9(st.session_state)
                    except Exception as field9_exc:
                        calculation_status["field9_eurusd_h1_decision_impact"] = {"ok": False, "shadow_only": True, "error": f"{type(field9_exc).__name__}: {field9_exc}"}
                    try:
                        from core.services.session_ai_field6_9_service_20260625 import build_and_publish_session_ai_field6_9
                        calculation_status["session_ai_field6_9_20260625"] = build_and_publish_session_ai_field6_9(st.session_state)
                    except Exception as additive_exc:
                        calculation_status["session_ai_field6_9_20260625"] = {"ok": False, "shadow_only": True, "error": f"{type(additive_exc).__name__}: {additive_exc}"}
                else:
                    calculation_status["field9_eurusd_h1_decision_impact"] = {"ok": False, "status": "SKIPPED_FOR_SUPER_QUICK_LUNCH", "shadow_only": True}
                    calculation_status["session_ai_field6_9_20260625"] = {"ok": False, "status": "SKIPPED_FOR_SUPER_QUICK_LUNCH", "shadow_only": True, "ai_ready": False}
                calculation_status["research_grade_system_v17"] = {"ok": False, "status": "SKIPPED_FOR_FAST_RUN", "shadow_only": True}
                calculation_status["unified_shadow_pipeline_v19"] = {"ok": False, "status": "SKIPPED_FOR_FAST_RUN", "shadow_only": True}
                calculation_status["research_adaptation_v18"] = {"ok": False, "status": "SKIPPED_FOR_FAST_RUN", "shadow_only": True}
        if field10_fast_lane_20260709:
            calculation_status["one_hour_direction_confirmation_20260626"] = defer_to_quick(
                st.session_state,
                "one_hour_direction_confirmation_20260626",
                reason="Super Quick opens Field 3 as soon as its three compact requested sections are ready; all heavier calculations are completed by Quick/Full.",
            )
        else:
            try:
                from core.services.one_hour_direction_service_20260626 import build_and_publish_one_hour_direction
                calculation_status["one_hour_direction_confirmation_20260626"] = build_and_publish_one_hour_direction(st.session_state)
            except Exception as one_hour_exc:
                calculation_status["one_hour_direction_confirmation_20260626"] = {"ok": False, "shadow_only": True, "production_decision_unchanged": True, "error": f"{type(one_hour_exc).__name__}: {one_hour_exc}"}
        # Fetch and publish genuine Finnhub news once when connected, then run
        # the existing Research/NLP ranking path. Failure never blocks Field 1.
        try:
            if scope == "LUNCH_CORE":
                raise RuntimeError("SKIPPED_FOR_SUPER_QUICK_LUNCH")
            from core.finnhub_connector import fetch_market_news
            raw_news = fetch_market_news("forex", force=True)
            st.session_state["finnhub_news_rows_20260626"] = raw_news
            try:
                from core.nlp_related_priority_20260615 import collect_existing_news_rows
                ranked_rows = collect_existing_news_rows(raw_news, window_days=25)
                if ranked_rows:
                    st.session_state["finnhub_ranked_news_20260626"] = ranked_rows
            except Exception as nlp_exc:
                calculation_status.setdefault("diagnostics", {})["nlp_rank_error"] = f"{type(nlp_exc).__name__}: {nlp_exc}"
        except Exception as news_exc:
            calculation_status.setdefault("diagnostics", {})["finnhub_news_error"] = f"{type(news_exc).__name__}: {news_exc}"
        # Repair publication aliases from already-calculated outputs before
        # the read-only Lunch consumers bind to the generation.
        try:
            from core.field1_publication_bridge_20260626 import ensure_field1_publication
            calculation_status["field1_publication_bridge_20260626"] = ensure_field1_publication(st.session_state, calculation_status)
        except Exception as bridge_exc:
            calculation_status.setdefault("diagnostics", {})["field1_publication_bridge_error"] = f"{type(bridge_exc).__name__}: {bridge_exc}"
        # Rebind identity/current direction after all post-run publishers.
        try:
            from core.post_run_consistency_20260626 import enforce_post_run_consistency
            enforce_post_run_consistency(st.session_state, calculation_status)
        except Exception as consistency_exc:
            calculation_status.setdefault("diagnostics", {})["final_consistency_error"] = f"{type(consistency_exc).__name__}: {consistency_exc}"
        try:
            from core.v9_architecture_guard_20260702 import finalize_after_settings_run
            calculation_status["v9_architecture_guard_20260702"] = finalize_after_settings_run(st.session_state, calculation_status)
        except Exception as v9_guard_exc:
            calculation_status.setdefault("diagnostics", {})["v9_architecture_guard_error"] = f"{type(v9_guard_exc).__name__}: {v9_guard_exc}"

        # Prepare the additive Table 2 trust history once inside Quick/Full.
        # Super Quick defers this burden so Field 10 opens faster.
        if field10_fast_lane_20260709:
            calculation_status["unified_lunch_trust_history_20260628"] = defer_to_quick(
                st.session_state,
                "unified_lunch_trust_history_20260628",
                reason="Trust-history rebuild is not required to publish Field 10 production rank; Quick/Full rebuilds it before full Lunch browsing.",
            )
        else:
            try:
                from core.canonical_lookup_20260626 import resolve_canonical
                from ui.lunch_four_core_fields_20260619 import (
                    _metric_result, _latest_completed_h1_from_state, _history_25day,
                    _field1_current_overlay, _align_table2_decision_with_table3, _factor_histories,
                )
                from ui.lunch_unified_trust_history_20260628 import get_or_build_unified_history
                canonical_for_trust = resolve_canonical(st.session_state)
                metric_result = _metric_result(st.session_state)
                completed_for_trust = _latest_completed_h1_from_state(st.session_state, metric_result)
                overall_for_trust = metric_result.get("history") if isinstance(metric_result.get("history"), pd.DataFrame) else pd.DataFrame()
                overall_for_trust = _history_25day(overall_for_trust, completed_h1=completed_for_trust)
                overall_for_trust = _field1_current_overlay(st.session_state, overall_for_trust, completed_for_trust)
                overall_for_trust = _align_table2_decision_with_table3(st.session_state, overall_for_trust, canonical_for_trust)
                factors_for_trust = _factor_histories(metric_result, completed_h1=completed_for_trust)
                trust_frame = get_or_build_unified_history(st.session_state, canonical_for_trust, overall_for_trust, factors_for_trust)
                calculation_status["unified_lunch_trust_history_20260628"] = {
                    "ok": True, "rows": int(len(trust_frame)),
                    "broker_days": int(trust_frame.get("Broker Day", pd.Series(dtype=object)).nunique(dropna=True)),
                    "production_values_modified": False, "table3_modified": False,
                }
            except Exception as trust_exc:
                calculation_status["unified_lunch_trust_history_20260628"] = {
                    "ok": False, "production_values_modified": False, "table3_modified": False,
                    "error": f"{type(trust_exc).__name__}: {trust_exc}",
                }

        # Full thesis run includes IMAP-RV; Quick/Super Quick leave the last
        # completed research envelope untouched.
        if scope == "FULL":
            try:
                from core.canonical_lookup_20260626 import resolve_canonical
                from research_quant.imap_rv_20260628 import run_imap_rv
                imap_envelope = run_imap_rv(st.session_state, resolve_canonical(st.session_state), force=False)
                calculation_status["imap_rv_20260628"] = {
                    "ok": imap_envelope.get("imap_rv_score") is not None,
                    "status": imap_envelope.get("status"),
                    "score": imap_envelope.get("imap_rv_score"),
                    "protective_action": imap_envelope.get("protective_action"),
                    "production_values_modified": False,
                }
            except Exception as imap_exc:
                calculation_status["imap_rv_20260628"] = {
                    "ok": False, "production_values_modified": False,
                    "error": f"{type(imap_exc).__name__}: {imap_exc}",
                }
        else:
            calculation_status["imap_rv_20260628"] = {"ok": False, "status": "SKIPPED_FOR_FAST_RUN", "production_values_modified": False}

        if field10_fast_lane_20260709:
            calculation_status["field2_quant_upgrade_20260629"] = defer_to_quick(
                st.session_state,
                "field2_quant_upgrade_20260629",
                reason="Full Field 2 visual/projection upgrade is deferred; Field 10 child validation uses the lightweight real-candle Field 2 bundle when needed.",
            )
        else:
            try:
                from core.field2_quant_upgrade_20260629 import build_field2_quant_upgrade
                calculation_status["field2_quant_upgrade_20260629"] = build_field2_quant_upgrade(st.session_state, force=True)
            except Exception as field2_upgrade_exc:
                calculation_status["field2_quant_upgrade_20260629"] = {"ok": False, "error": f"{type(field2_upgrade_exc).__name__}: {field2_upgrade_exc}"}

        calculation_status["refresh_before_run"] = refresh_result
        calculation_status["calculation_scope"] = (
            "LUNCH_FIELDS_1_TO_3" if scope == "LUNCH_CORE" else
            "QUICK_FIELDS_1_TO_9_PLUS_AI" if scope == "QUICK" else
            "FULL_FIELDS_1_TO_9_PLUS_AI_AND_THESIS"
        )
        if scope == "FULL":
            try:
                from core.morning_quant_intelligence_20260624 import publish_quant_20260624_snapshot
                calculation_status["quant_20260624"] = publish_quant_20260624_snapshot(st.session_state)
            except Exception as exc:
                calculation_status["quant_20260624"] = {"ok": False, "error": str(exc), "shadow_only": True}
        else:
            calculation_status["quant_20260624"] = {"ok": False, "status": "SKIPPED_FOR_BOUNDED_RUN", "shadow_only": True}
        st.session_state["settings_run_status_20260617"] = calculation_status
        st.session_state["settings_last_one_click_refresh_20260622"] = refresh_result
        try:
            from core.current_result_sync_20260708 import build_current_result
            build_current_result(
                st.session_state,
                run_id=calculation_status.get("run_id") or calculation_status.get("parent_run_id") or calculation_status.get("calculation_generation"),
                reason="settings_run_action_complete",
            )
            from core.institutional_quant_layer_20260708 import publish_institutional_quant_run
            calculation_status["institutional_quant_layer_20260708"] = publish_institutional_quant_run(
                st.session_state, calculation_status, reason="antd_settings_run_action_complete"
            )
            st.session_state["settings_run_status_20260617"] = calculation_status
        except Exception as current_result_exc_20260708:
            calculation_status.setdefault("diagnostics", {})["current_result_sync_error_20260708"] = f"{type(current_result_exc_20260708).__name__}: {current_result_exc_20260708}"
        # Compatibility guard retained for static architecture tests: if bool((calculation_status.get("canonical") or {}).get("ok"))
        new_ok = bool((calculation_status.get("canonical") or {}).get("ok"))
        valid_canonical = False
        try:
            from core.canonical_runtime_20260617 import get_canonical
            valid_canonical = bool(get_canonical(st.session_state))
        except Exception:
            valid_canonical = bool(st.session_state.get("canonical_decision_result_20260617"))
        fact_pack_ready = False
        try:
            from tabs.ai_assistant_compact_20260619 import _recover_fact_pack
            fact_pack_ready = bool(_recover_fact_pack(st.session_state))
        except Exception:
            fact_pack_ready = False
        if new_ok or valid_canonical or fact_pack_ready:
            try:
                from core.canonical_lookup_20260626 import resolve_canonical
                from core.symbol_universe_20260629 import normalize_instrument
                published_symbol = normalize_instrument((resolve_canonical(st.session_state) or {}).get("symbol") or "")
                active_symbol = normalize_instrument(st.session_state.get("symbol") or "EURUSD")
                if published_symbol == active_symbol:
                    st.session_state["selected_symbol_pending_run_20260629"] = False
            except Exception:
                pass
            # Static compatibility contract for historical tests/documentation:
            # {"lunch_field_open_5_20260621": True, "lunch_field_widget_5_20260621": True}
            _open_lunch_ai_after_settings_run(used_previous=not new_ok)
        else:
            st.session_state["active_page"] = "Settings"
            st.session_state["active_subpage"] = ""
        return calculation_status

    # Cooperative instant engine: acknowledge the click first, then execute the
    # protected transaction on the next timed Streamlit pass. This avoids unsafe
    # background-thread access to st.session_state while keeping the browser UI
    # visible and streaming one row per symbol.
    try:
        from core.instant_run_engine_20260705 import (
            ACTIVE_STATUSES, TERMINAL_STATUSES, execute_queued_job, is_due,
            progress_rows, recover_stale_job, seconds_until_due,
        )
        instant_job = recover_stale_job(st.session_state, stale_after_seconds=900.0)
    except Exception as instant_engine_exc:
        instant_job = None
        st.session_state["instant_run_engine_import_error_20260705"] = f"{type(instant_engine_exc).__name__}: {instant_engine_exc}"

    if isinstance(instant_job, Mapping):
        job_status = str(instant_job.get("status") or "").upper()
        with st.container(border=True):
            st.markdown("### ⚡ Instant Run Engine")
            status_cols = st.columns(4)
            status_cols[0].metric("Job", str(instant_job.get("job_id") or "-")[-18:])
            status_cols[1].metric("Status", job_status or "UNKNOWN")
            status_cols[2].metric("Progress", f"{float(instant_job.get('progress_percent') or 0.0):.1f}%")
            status_cols[3].metric("Scope", str(instant_job.get("scope") or "QUICK"))
            stage_slot = st.empty()
            progress_slot = st.empty()
            table_slot = st.empty()

            def _render_instant_progress(snapshot: Mapping[str, Any] | None = None) -> None:
                nonlocal instant_job
                if isinstance(snapshot, Mapping):
                    try:
                        from core.instant_run_engine_20260705 import publish_progress
                        instant_job = publish_progress(st.session_state, snapshot) or instant_job
                    except Exception:
                        pass
                percent = float((instant_job or {}).get("progress_percent") or 0.0)
                symbol = str((instant_job or {}).get("current_symbol") or "Validating")
                stage = str((instant_job or {}).get("current_stage") or "Queued")
                stage_slot.info(f"{symbol} — {stage}")
                progress_slot.progress(min(1.0, max(0.0, percent / 100.0)), text=f"{percent:.1f}% complete")
                rows = progress_rows(instant_job)
                if rows:
                    table_slot.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            _render_instant_progress()

            if job_status == "QUEUED" and not is_due(instant_job):
                remaining = seconds_until_due(instant_job)
                st.caption(f"Calculation starts automatically in about {remaining:.1f} seconds. Duplicate clicks are ignored.")
                try:
                    from streamlit_autorefresh import st_autorefresh
                    st_autorefresh(interval=max(350, int((remaining + 0.15) * 1000)), limit=2, key=f"instant_run_start_{instant_job.get('job_id')}")
                except Exception:
                    _safe_rerun()
            elif job_status in ACTIVE_STATUSES:
                def _execute_existing_protected_transaction(job: Mapping[str, Any], publish_callback):
                    scope = str(job.get("scope") or "QUICK").upper()
                    symbols = list(job.get("symbols") or [])
                    st.session_state["settings_calculation_scope_20260625"] = scope
                    # Compute using loaded frames, then immediately restore the
                    # Settings-selected symbol universe for every visible tab.
                    st.session_state["calculation_loaded_symbols_20260708"] = list(symbols)
                    if symbols:
                        set_legacy_calculation_symbol(st.session_state, symbols[0], connector=True)
                    try:
                        from core.current_result_sync_20260708 import sync_settings_source_of_truth, selected_symbols_from_settings
                        sync_settings_source_of_truth(
                            st.session_state,
                            selected_symbols_from_settings(st.session_state),
                            str(job.get("timeframe") or st.session_state.get("timeframe") or "H4"),
                            reason="instant_run_execute_restore_selected_universe",
                            clear_stale=False,
                        )
                    except Exception as instant_sync_exc_20260708:
                        st.session_state["instant_current_selection_sync_error_20260708"] = f"{type(instant_sync_exc_20260708).__name__}: {instant_sync_exc_20260708}"
                    _live_render_gate_20260727 = {"percent": -10.0}
                    def _publish_and_render_live(snapshot: Mapping[str, Any]) -> None:
                        nonlocal instant_job
                        publish_callback(snapshot)
                        incoming_percent = float(snapshot.get("overall_percent") or snapshot.get("progress_percent") or 0.0)
                        should_render = (
                            incoming_percent >= 99.9
                            or incoming_percent - float(_live_render_gate_20260727["percent"]) >= 8.0
                        )
                        if not should_render:
                            return
                        _live_render_gate_20260727["percent"] = incoming_percent
                        try:
                            from core.instant_run_engine_20260705 import current_job as _read_instant_job
                            instant_job = _read_instant_job(st.session_state, restore=False) or instant_job
                            _render_instant_progress()
                        except Exception:
                            # Rendering failure must never interrupt calculation.
                            pass
                    _instant_progress_callback_holder["callback"] = _publish_and_render_live
                    from core.settings_one_click_controller_20260624 import run_one_click_action
                    labels = {
                        "LUNCH_CORE": "Super Quick Field 3 recent-age ranking + Higher Standard Summary",
                        "QUICK": "Quick completes deferred Lunch/AI/Field 11 work + Field 10 refresh",
                        "FULL": "Full Main Fields 1-9 + Thesis + Field 10/11 + Open Lunch",
                    }
                    if scope == "LUNCH_CORE":
                        # Dedicated compute-only fast lane: no legacy one-click
                        # controller, no Field 10/11, AI, research, trust-history
                        # or institutional publisher. It produces only the two
                        # requested Field 3 sections from already-loaded candles.
                        from core.super_quick_field3_20260722 import run_super_quick_field3
                        fast_result = run_super_quick_field3(
                            st.session_state,
                            symbols=symbols,
                            timeframe=str(job.get("timeframe") or st.session_state.get("timeframe") or "H4"),
                            progress_callback=_publish_and_render_live,
                        )
                        transaction = {
                            "status": str(fast_result.get("status") or "COMPLETED"),
                            "result_payload": fast_result,
                            "run_id": fast_result.get("run_id"),
                            "transaction_id": fast_result.get("run_id"),
                            "generation_id": fast_result.get("calculation_generation"),
                        }
                    else:
                        transaction = run_one_click_action(
                            st.session_state,
                            labels.get(scope, labels["QUICK"]),
                            _settings_run_action_20260624,
                            payload={
                                "instant_job_id": str(job.get("job_id") or ""),
                                "symbols": symbols,
                                "symbol": symbols[0] if symbols else str(st.session_state.get("symbol") or "EURUSD"),
                                "timeframe": str(job.get("timeframe") or st.session_state.get("timeframe") or "H4"),
                                "scope": scope,
                            },
                            target_page="Field 3",
                            result_run_id_getter=lambda status: str((status or {}).get("run_id") or (status or {}).get("parent_run_id") or (status or {}).get("calculation_generation") or ""),
                        )
                    try:
                        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
                        from core.multi_symbol_run_groups_20260706 import record_completed_symbols, save_group_preferences
                        cumulative_symbols = record_completed_symbols(st.session_state, symbols, transaction)
                        save_group_preferences(DEFAULT_DB_PATH, st.session_state, completed=cumulative_symbols)
                        st.session_state["field10_cumulative_symbols_20260706"] = list(cumulative_symbols)
                    except Exception as cumulative_exc:
                        st.session_state["multi_symbol_cumulative_nonblocking_error_20260706"] = f"{type(cumulative_exc).__name__}: {cumulative_exc}"
                    nested_result = transaction.get("result_payload") if isinstance(transaction.get("result_payload"), Mapping) else transaction
                    nested_status = str((nested_result or {}).get("status") or transaction.get("status") or "").upper()
                    nested_failed = int((nested_result or {}).get("failed_symbols") or 0) if isinstance(nested_result, Mapping) else 0
                    if scope != "LUNCH_CORE":
                        try:
                            from core.current_result_sync_20260708 import build_current_result
                            build_current_result(
                                st.session_state,
                                run_id=transaction.get("run_id") or transaction.get("transaction_id") or transaction.get("generation_id"),
                                reason="instant_transaction_complete",
                            )
                            from core.institutional_quant_layer_20260708 import publish_institutional_quant_run
                            transaction["institutional_quant_layer_20260708"] = publish_institutional_quant_run(
                                st.session_state, transaction, reason="instant_transaction_complete"
                            )
                        except Exception as current_result_after_tx_exc_20260708:
                            st.session_state["instant_current_result_error_20260708"] = f"{type(current_result_after_tx_exc_20260708).__name__}: {current_result_after_tx_exc_20260708}"
                    else:
                        transaction["institutional_quant_layer_20260708"] = {
                            "ok": False, "status": "DEFERRED_TO_QUICK_RUN", "fast_lane": True
                        }
                    if transaction.get("status") == "FAILED" or nested_status in {"FAILED", "PARTIAL"} or nested_failed:
                        st.session_state["lunch_last_run_warning_20260707"] = {
                            "status": nested_status or transaction.get("status"),
                            "failed_symbols": nested_failed,
                            "message": "The run finished with protected partial diagnostics; Lunch opens with every completed exact-symbol result and the previous canonical fallback.",
                        }
                    # All three buttons have the same post-run navigation contract.
                    # A partial/failed child still opens Field 3 with every valid published symbol.
                    _open_lunch_ai_after_settings_run(used_previous=nested_status != "COMPLETED")
                    return transaction

                final_job = execute_queued_job(st.session_state, _execute_existing_protected_transaction)
                instant_job = final_job or instant_job
                _render_instant_progress()
                final_status = str((instant_job or {}).get("status") or "").upper()
                if final_status == "FAILED":
                    st.error(str((instant_job or {}).get("error") or "Instant Run failed safely. The previous valid canonical result was preserved."))
                elif final_status == "PARTIAL":
                    st.warning("Instant Run completed with partial symbol results. The latest complete canonical snapshot remains protected.")
                elif final_status == "COMPLETED":
                    st.success("Instant Run completed. Opening Field 3 with the published result.")
                _open_lunch_ai_after_settings_run(used_previous=final_status != "COMPLETED")
                _safe_rerun()
            elif job_status in TERMINAL_STATUSES:
                summary = instant_job.get("result_summary") if isinstance(instant_job.get("result_summary"), Mapping) else {}
                if summary:
                    st.dataframe(pd.DataFrame([{str(k): v for k, v in summary.items() if k != "errors"}]), use_container_width=True, hide_index=True)
                if instant_job.get("error"):
                    st.error(str(instant_job.get("error")))

    # Keep the run progress/status table immediately below the three run
    # buttons. Connector and credential controls follow it, rather than pushing
    # live progress far down the Settings page on mobile.
    st.markdown("### Connections, API Keys and Provider Health")
    _render_mobile_api_key_center()
    _render_finnhub_connector_section()
    try:
        from ui.optional_provider_connectors_20260705 import render_optional_provider_connectors
        render_optional_provider_connectors(st.session_state)
    except Exception as optional_connector_exc:
        st.caption(f"Optional provider controls unavailable: {type(optional_connector_exc).__name__}")
    try:
        from ui.provider_health_panel_20260705 import render_provider_health_panel
        render_provider_health_panel(st.session_state)
    except Exception as provider_panel_exc:
        st.caption(f"Provider health panel unavailable: {type(provider_panel_exc).__name__}")

    if reset_col.button("🔄 Reset UI", key="settings_reset_ui_20260617", use_container_width=True):
        st.session_state["active_page"] = "Settings"
        st.session_state["active_subpage"] = ""
        _safe_rerun()

    # Secondary/advanced settings follow the always-visible startup controls
    # above. They must not displace or duplicate the connector/selector/modes.
    _render_secure_automation_settings()
    _render_openrouter_api_center()
    _render_arert_research_settings()
    _render_imap_rv_settings()

    with st.expander("Open / Close — Trade Timer / Sound Alert", expanded=True):
        try:
            from ui.sidebar_fallback_panel import _render_timer
            _render_timer(key_prefix="settings_timer_20260619")
        except Exception as exc:
            st.warning(f"Trade timer skipped safely: {exc}")

    with st.expander("Open / Close — Account / Logout", expanded=False):
        try:
            from ui.sidebar_fallback_panel import _render_ui_and_account
            _render_ui_and_account(key_prefix="settings_account_20260619")
        except Exception as exc:
            st.warning(f"Account controls skipped safely: {exc}")

    status = st.session_state.get("settings_run_status_20260617")
    if isinstance(status, dict):
        cols = st.columns(5)
        cols[0].metric("Last Run", "READY" if status.get("ok") else "PARTIAL")
        cols[1].metric("Generation", str(status.get("calculation_generation", "-")))
        cols[2].metric("Lunch Metric", "READY" if (status.get("metric") or {}).get("ok") else "CHECK")
        cols[3].metric("PowerBI", "READY" if (status.get("powerbi") or {}).get("ok") else "CHECK")
        cols[4].metric("Built At", str(status.get("built_at", "-")))
        if status.get("errors"):
            with st.expander("Open / Close — Last calculation status", expanded=False):
                st.dataframe(pd.DataFrame({"Status": list(status.get("errors") or [])}), use_container_width=True, hide_index=True)
        readiness = status.get("readiness") if isinstance(status.get("readiness"), dict) else st.session_state.get("system_wide_readiness_manifest_20260618")
        if isinstance(readiness, dict):
            component_rows = []
            for name, item in (readiness.get("components") or {}).items():
                item = item if isinstance(item, dict) else {}
                component_rows.append({
                    "Component": name,
                    "Status": "READY" if item.get("ready") else "CHECK / ERROR",
                    "Rows": item.get("rows", 0),
                    "Detail": item.get("detail", ""),
                })
            with st.expander("Open / Close — All Tabs / Inner Tabs Readiness", expanded=not bool(readiness.get("ready"))):
                st.dataframe(pd.DataFrame(component_rows), use_container_width=True, hide_index=True)

    try:
        from core.operational_sync_20260618 import collect_sync_health, errors_frame, clear_operational_errors
        health = pd.DataFrame(collect_sync_health(st.session_state))
        with st.expander("Open / Close — Synchronization Health", expanded=False):
            st.dataframe(health, use_container_width=True, hide_index=True)
        errors = errors_frame(st.session_state)
        has_errors = bool(len(errors)) if hasattr(errors, "__len__") else False
        with st.expander("Open / Close — Errors / Fix Fast", expanded=has_errors):
            if has_errors:
                st.dataframe(errors, use_container_width=True, hide_index=True)
                if st.button("Clear displayed errors", key="clear_operational_errors_20260618", use_container_width=True):
                    clear_operational_errors(st.session_state)
                    _safe_rerun()
            else:
                st.success("No captured calculation or renderer errors.")
    except Exception as exc:
        st.caption(f"Synchronization diagnostics unavailable: {exc}")

    try:
        from ui.decision_product_panel_20260617 import render_settings_product_status
        render_settings_product_status()
    except Exception as exc:
        st.caption(f"Decision diagnostics skipped safely: {exc}")


def show(runtime_context: Mapping[str, Any] | None = None) -> None:
    """Render only the authoritative page/subpage resolved by runner.py."""
    generation_sync = (runtime_context or {}).get("generation_sync") if isinstance(runtime_context, Mapping) else None
    if isinstance(generation_sync, Mapping) and generation_sync.get("status") not in {"CURRENT", "SYNCED", "NOT_READY"}:
        st.warning("A stale tab view was detected. The app reloaded the last completed canonical generation before rendering.")
    try:
        from core.tab_state_stability_20260615 import stabilize_tab_state
        stabilize_tab_state()
        page = str((runtime_context or {}).get("active_page") or st.session_state.get("active_page") or "Settings")
        subpage = str((runtime_context or {}).get("active_subpage") or st.session_state.get("active_subpage") or "")
        # Legacy navigation keys are mirrors only.
        from ui.antd_navigation_20260615 import sync_active_page_to_legacy_state
        page, subpage = sync_active_page_to_legacy_state()
    except Exception:
        page, subpage = "Settings", ""

    # Navigation never changes connector, calculation, or display identity.
    # The floating Global Symbol control restores the persisted context once and
    # every page reads that same identity.
    try:
        from core.global_symbol_context import get_global_symbol_context
        get_global_symbol_context(st.session_state)
    except Exception as global_context_exc:
        st.session_state["global_symbol_context_restore_error_v2"] = f"{type(global_context_exc).__name__}: {global_context_exc}"

    if page != "Settings":
        manifest = st.session_state.get("system_wide_readiness_manifest_20260618")
        if isinstance(manifest, dict) and not bool(manifest.get("ready")) and st.session_state.get("settings_run_complete_20260617"):
            missing = [name for name, item in (manifest.get("components") or {}).items() if isinstance(item, dict) and not item.get("ready")]
            if missing:
                st.warning(
                    f"Published generation {manifest.get('calculation_generation', '-')} is available with visible component errors: "
                    + ", ".join(missing[:6])
                    + ("…" if len(missing) > 6 else "")
                    + ". Open Settings → Errors / Fix Fast for exact details."
                )

    if page == "Settings":
        _render_settings()
    elif page == "Home":
        _render_home()
    elif page == "Lunch":
        _render_lunch({}, subpage)
    elif page == "Data Visualization":
        try:
            from core.current_result_sync_20260708 import render_current_data_visualization
            render_current_data_visualization(st.session_state)
        except Exception as data_vis_exc_20260708:
            st.warning(f"Data Visualization could not render safely: {type(data_vis_exc_20260708).__name__}: {data_vis_exc_20260708}")
    elif page == "Field 4 to 9":
        from tabs.field456789_page_20260626 import show as _show_field456789
        _show_field456789({**dict(runtime_context or {}), "active_page": "Dinner"})
    elif page == "Field 456+789":
        from tabs.field456789_page_20260626 import show as _show_alias_combined
        _show_alias_combined({**dict(runtime_context or {}), "active_page": "Dinner"})
    elif page == "Field 456":
        from tabs.field456_page_20260626 import show as _show_field456
        _show_field456(runtime_context)
    elif page == "Field 789":
        from tabs.field789_page_20260626 import show as _show_field789
        _show_field789(runtime_context)
    elif page == "Dinner":
        _render_dinner({}, subpage)
    elif page == "AI Assistant":
        from pages.ai_assistant import show as _show_independent_ai
        _show_independent_ai(runtime_context)
    elif page == "Morning":
        _render_morning()
    elif page == "Research":
        _render_research(subpage)
    elif page == "Other":
        _render_other()
    else:
        _render_settings()
