"""Main-page replacement for the native sidebar controls.

This panel mirrors the critical sidebar functions with unique widget keys, so it
can be rendered at the same time as the native sidebar without duplicate-key
crashes. It writes to the same session_state fields used by the original sidebar
connector/timer logic.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence
import time
import streamlit as st

try:
    from core.navigation_parts.state import _normalize_symbol, _safe_log_event
except Exception:
    def _normalize_symbol(x): return str(x or "EURUSD").upper().replace("/", "").replace(" ", "")
    def _safe_log_event(message): pass

try:
    from core.navigation_parts.connection import _connect_now
except Exception:
    def _connect_now(label="Connect", quick=False, force=False):
        st.warning("Connector function is unavailable. Native sidebar backup may still work.")

try:
    from core.navigation_parts.panels import _disconnect_shared_state
except Exception:
    def _disconnect_shared_state(reason="manual disconnect"):
        for k in ["connected", "source", "last_df", "last_fetch", "last_connection_error", "last_connection_message", "last_connection_rows"]:
            st.session_state.pop(k, None)
        st.session_state.connected = False
        st.session_state.source = "DISCONNECTED"
        st.session_state.last_connection_message = reason

def request_open_native_sidebar():
    # Native sidebar is optional backup only; no JavaScript DOM open is used.
    try:
        from ui.sidebar_hard_lock import enable_native_sidebar_backup
        enable_native_sidebar_backup()
    except Exception:
        pass

def request_close_native_sidebar():
    # Compatibility with older calls. No JavaScript DOM close attempt is used,
    # and this no longer locks the sidebar OFF. It only records close intent so
    # the native backup can always open again after any button click.
    try:
        from ui.sidebar_hard_lock import init_sidebar_policy, inject_sidebar_policy_css
        init_sidebar_policy()
        st.session_state["sidebar_close_requested_native_only"] = True
        st.session_state["new7_native_sidebar_status_20260614"] = "Close requested; native backup remains available."
        inject_sidebar_policy_css()
    except Exception:
        pass


def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _selected_symbols_from_state() -> list[str]:
    raw = st.session_state.get("multi_symbol_selected_20260701")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Sequence) or isinstance(raw, (bytes, bytearray)):
        return []
    selected: list[str] = []
    for value in raw:
        symbol = str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")
        if symbol and symbol not in selected:
            selected.append(symbol)
    return selected




def _provider_route_labels(mode: str | None = None) -> tuple[str, str, tuple[str, ...]]:
    """Return selected Twelve Data key-pool route labels."""
    normalized_mode = str(mode or st.session_state.get("connector_mode") or "twelve_pool").strip().lower()
    try:
        from core.data.market_data_orchestrator import provider_priority_for_state
        route = tuple(provider_priority_for_state({"connector_mode": normalized_mode}))
    except Exception:
        route = ("TWELVE_DATA_KEY_POOL", "FINNHUB", "LOCAL_VALID_CACHE")
    preferred = str(route[0] if route else "TWELVE_DATA_KEY_POOL").upper()
    fallback = str(route[1] if len(route) > 1 else "LOCAL_VALID_CACHE").upper()
    return preferred, fallback, route


def _resolved_secret_value(logical_name: str, session_key: str) -> str:
    """Resolve Streamlit Secrets/env/session API keys without logging them."""
    try:
        from core.secure_api_startup_20260619 import resolve_api_key
        value = str(resolve_api_key(logical_name, st.session_state) or "").strip()
    except Exception:
        value = ""
    if not value:
        value = str(st.session_state.get(session_key) or "").strip()
    return value
def _mapping_from_state(key: str) -> dict:
    value = st.session_state.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _central_market_connect(*, force: bool) -> dict:
    """Use one secret-aware, quota-safe path for every market connection."""
    from core.connector_state_machine_20260621 import begin, fail, succeed

    selected = _selected_symbols_from_state()
    symbol = str(
        st.session_state.get("multi_symbol_main_symbol_20260702")
        or (selected[0] if selected else st.session_state.get("symbol") or "EURUSD")
    ).strip().upper().replace("/", "").replace(" ", "")
    timeframe = str(st.session_state.get("timeframe") or "H4").strip().upper()
    bars = int(st.session_state.get("connector_bars", 600) or 600)
    mode = str(st.session_state.get("connector_mode") or "twelve_pool").lower()
    signature = f"{mode}|{symbol}|{timeframe}|{bars}|{'|'.join(selected)}"

    saved = st.session_state.get("market_connector_saved_profile_20260702")
    if (
        not force
        and isinstance(saved, dict)
        and str(saved.get("signature") or "") == signature
        and bool(st.session_state.get("connected"))
        and st.session_state.get("last_df") is not None
    ):
        result = {
            "ok": True,
            "status": "REUSED_CONNECTED_PROFILE",
            "message": "The identical validated connector profile was restored without a new API request.",
            "symbol": symbol,
            "timeframe": timeframe,
        }
        st.session_state["last_refresh_result_20260621"] = result
        succeed(
            st.session_state,
            "market_connector_20260621",
            result["message"],
            connection_state=str(saved.get("connection_state") or st.session_state.get("market_connection_outcome_20260708") or "CONNECTED"),
        )
        return result

    begin(st.session_state, "market_connector_20260621")
    if force:
        st.session_state["explicit_connector_refresh_20260705"] = True
    from core.app.refresh import refresh_data
    result = refresh_data(st.session_state, symbol_override=symbol, timeframe_override=timeframe)

    provenance = _mapping_from_state("active_symbol_market_provenance_20260705")
    attempts_raw = provenance.get("attempts")
    attempts = list(attempts_raw) if isinstance(attempts_raw, Sequence) and not isinstance(attempts_raw, (str, bytes, bytearray)) else []
    active_provider = str(result.get("source") or result.get("provider") or provenance.get("provider") or "").upper()
    selected_provider = "TWELVE_DATA_KEY_POOL" if mode in {"twelve_pool", "twelve", "fallback"} else mode.upper()
    selected_attempt = next((item for item in attempts if str(item.get("provider") or "").upper() == selected_provider), {})
    selected_ok = bool(selected_attempt.get("ok")) or (bool(result.get("ok")) and active_provider == selected_provider)
    preferred_provider, fallback_provider, provider_route = _provider_route_labels(mode)
    st.session_state["selected_market_provider_20260707"] = selected_provider
    st.session_state["selected_market_provider_connected_20260707"] = selected_ok
    st.session_state["active_market_provider_20260707"] = active_provider or "NONE"
    st.session_state["active_market_provider_20260705"] = preferred_provider
    st.session_state["fallback_market_provider_20260705"] = fallback_provider
    st.session_state["market_data_provider_order_override_20260708"] = provider_route
    st.session_state["actual_market_provider_used_20260708"] = active_provider or "NONE"

    key_pool_attempt = next((item for item in attempts if isinstance(item, Mapping) and str(item.get("provider") or "").upper() in {"TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA"}), {})
    key_pool_ok = bool(key_pool_attempt.get("ok")) or (bool(result.get("ok")) and active_provider in {"TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA"})
    key_pool_message = str(key_pool_attempt.get("message") or key_pool_attempt.get("category") or (result.get("message") if key_pool_ok else "Twelve Data key pool did not supply validated candles.") or "")
    st.session_state["twelve_data_key_pool_connected"] = key_pool_ok
    st.session_state["twelve_data_key_pool_last_message"] = key_pool_message
    st.session_state["twelve_data_key_pool_last_checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if key_pool_ok:
        st.session_state["twelve_data_key_pool_last_success_at"] = st.session_state["twelve_data_key_pool_last_checked_at"]
    twelve_attempt = next((item for item in attempts if isinstance(item, Mapping) and str(item.get("provider") or "").upper() in {"TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA"}), {})
    twelve_ok = bool(twelve_attempt.get("ok")) or (
        bool(result.get("ok")) and str(result.get("source") or result.get("provider") or "").upper() in {"TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA"}
    )
    twelve_message = str(
        twelve_attempt.get("message")
        or twelve_attempt.get("category")
        or (result.get("message") if twelve_ok else "Twelve Data key pool was not required or did not supply validated candles.")
        or ""
    )
    st.session_state["twelve_data_connected"] = twelve_ok
    st.session_state["twelve_data_last_message"] = twelve_message
    st.session_state["twelve_data_last_checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if twelve_ok:
        st.session_state["twelve_data_last_success_at"] = st.session_state["twelve_data_last_checked_at"]

    if result.get("ok"):
        st.session_state["market_connector_saved_profile_20260702"] = {
            "signature": signature,
            "connection_state": str(result.get("connection_state") or st.session_state.get("market_connection_outcome_20260708") or "CONNECTED"),
            "mode": mode,
            "main_symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "selected_symbols": selected or [symbol],
        }
        succeed(
            st.session_state, "market_connector_20260621",
            str(result.get("message") or "Connected"),
            connection_state=str(result.get("connection_state") or st.session_state.get("market_connection_outcome_20260708") or "CONNECTED"),
        )
    else:
        fail(st.session_state, "market_connector_20260621", str(result.get("message") or "Connection failed"))

    try:
        from core.connectors.credential_vault import mark_connection
        from core.secure_api_startup_20260619 import resolve_api_key
        mark_connection(
            "TWELVE_DATA_KEY_POOL",
            connected=key_pool_ok,
            configured=bool(resolve_api_key("second_api", st.session_state) or st.session_state.get("twelve_api_key_1") or st.session_state.get("twelve_api_key_2")),
            status="VALIDATED" if key_pool_ok else str(key_pool_attempt.get("category") or result.get("status") or "NOT_CONNECTED"),
            error_code="" if key_pool_ok else str(key_pool_attempt.get("category") or result.get("status") or "NOT_CONNECTED"),
        )
    except Exception:
        pass
    return result


def _market_connect_callback(key_prefix: str) -> None:
    """Connect once or reuse the identical saved profile without a new request."""
    _central_market_connect(force=False)
    request_close_native_sidebar()


def _market_refresh_callback(key_prefix: str) -> None:
    """Explicitly refresh the saved main-symbol feed through the quota guard."""
    _central_market_connect(force=True)
    request_close_native_sidebar()


def _market_disconnect_callback() -> None:
    _disconnect_shared_state("manual market disconnect")
    try:
        from core.connector_state_machine_20260621 import disconnect
        disconnect(st.session_state, "market_connector_20260621", "Disconnected by user.")
    except Exception:
        pass
    request_close_native_sidebar()

def _fmt_timer(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def render_native_sidebar_js_controls() -> None:
    st.markdown('<div class="new7-card"><b>🧭 Native Sidebar Backup</b><br><span style="color:#64748b;font-size:.78rem;">Native sidebar is optional backup only. No JavaScript open/close buttons are used.</span></div>', unsafe_allow_html=True)


def _render_connector_status_only() -> None:
    """Read-only connector status for menu/sidebar surfaces.

    API secret inputs live only in Settings, preventing duplicate password fields
    and widget state conflicts in the sidebar, drawer and NLP workspace.
    """
    st.markdown("#### 🔌 Connector Status")
    try:
        rows = len(st.session_state.get("last_df")) if st.session_state.get("last_df") is not None else 0
    except Exception:
        rows = 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Market API", str(st.session_state.get("source", "DISCONNECTED") or "DISCONNECTED"))
    c2.metric("Symbol / TF", f"{st.session_state.get('symbol','EURUSD')} / {st.session_state.get('timeframe','H4')}")
    c3.metric("Rows", f"{rows:,}")
    try:
        from core.finnhub_connector import connection_status
        status = connection_status()
        f1, f2 = st.columns(2)
        f1.metric("Finnhub", "CONNECTED" if status.get("connected") else "DISCONNECTED")
        f2.metric("Availability", status.get("availability", "UNKNOWN"))
    except Exception as exc:
        st.caption(f"Finnhub status unavailable: {str(exc)[:100]}")
    st.caption("API keys are entered once in Settings only.")
    if st.button("⚙️ Open Settings API Controls", key="open_settings_api_controls_20260618", use_container_width=True):
        st.session_state["active_page"] = "Settings"
        st.session_state["active_subpage"] = ""
        st.session_state["tab_choice"] = "Settings"
        _safe_rerun()


def _render_connector(*, key_prefix: str = "main_drawer", show_secret_inputs: bool = True, show_symbol_selector: bool = False) -> None:
    st.markdown("#### 🔌 API / Data Connection")
    # Symbol ownership belongs to the one ordered Multi-Symbol Selector.  The
    # connector intentionally renders no legacy single-symbol library/text box,
    # preventing duplicate hidden widgets and stale USDCHF overrides.
    if show_symbol_selector:
        try:
            from ui.multi_symbol_settings_20260701 import render_multi_symbol_selector
            render_multi_symbol_selector(st.session_state)
        except Exception as symbol_exc:
            try:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error("connector.multi_symbol_selector", symbol_exc)
            except Exception:
                incident = "symbol-selector"
            st.warning(f"The multi-symbol selector could not load here. Open Settings and retry. Support reference: {incident}.")
    else:
        selected = _selected_symbols_from_state()
        main = str(st.session_state.get("multi_symbol_main_symbol_20260702") or (selected[0] if selected else st.session_state.get("symbol") or "EURUSD"))
        st.caption(f"Main Core Symbol: {main} · Change instruments only in the Multi-Symbol Selector below.")

    connector_options = ["twelve_pool", "twelve", "fallback", "safe_demo"]
    current_mode = st.session_state.get("connector_mode", "twelve_pool")
    if current_mode in {"finnhub", "mt5", "doo_bridge"}:
        current_mode = "twelve_pool"
    if current_mode not in connector_options:
        current_mode = "twelve_pool"
    connector_mode = st.selectbox(
        "API source",
        connector_options,
        index=connector_options.index(current_mode),
        key=f"{key_prefix}_connector_mode_v1",
    )
    st.session_state.connector_mode = connector_mode

    tfs = ["M1", "M2", "M5", "M15", "H1", "H4", "D1", "CUSTOM"]
    current_tf = str(st.session_state.get("timeframe", "H1") or "H1").upper()
    if current_tf not in tfs:
        current_tf = "H1"
    timeframe = st.selectbox(
        "Timeframe",
        tfs,
        index=tfs.index(current_tf),
        key=f"{key_prefix}_timeframe_v1",
        help="CUSTOM loads H1 as main data and M1 only as confirmation data.",
    )
    st.session_state.timeframe = timeframe

    bars = st.number_input(
        "Candles / bars",
        min_value=100,
        max_value=250000,
        value=int(st.session_state.get("connector_bars", 600) or 600),
        step=100,
        key=f"{key_prefix}_connector_bars_v1",
    )
    st.session_state.connector_bars = int(bars)

    if connector_mode in ["twelve_pool", "twelve", "fallback"] and show_secret_inputs:
        existing_twelve_key = _resolved_secret_value("second_api", "twelve_api_key")
        if existing_twelve_key and not str(st.session_state.get("twelve_api_key_1") or "").strip():
            st.session_state["twelve_api_key_1"] = existing_twelve_key
            st.session_state["twelve_api_key"] = existing_twelve_key
            st.session_state["TWELVE_DATA_API_KEY"] = existing_twelve_key
            st.session_state["twelve_api_key_source"] = "auto_secret"
        entered_key_1 = st.text_input(
            "Twelve Data API Key 1", value=st.session_state.get("twelve_api_key_1", st.session_state.get("twelve_api_key", "")),
            type="password", key=f"{key_prefix}_twelve_api_key_1_v1",
        )
        entered_key_2 = st.text_input(
            "Twelve Data API Key 2", value=st.session_state.get("twelve_api_key_2", ""),
            type="password", key=f"{key_prefix}_twelve_api_key_2_v1",
        )
        st.session_state["enable_twelve_multi_key_loading"] = st.checkbox(
            "Enable Multi-Key Loading", value=bool(st.session_state.get("enable_twelve_multi_key_loading", True)),
            key=f"{key_prefix}_enable_twelve_multi_key_loading_v1",
        )
        if str(entered_key_1 or "").strip() or not st.session_state.get("twelve_api_key_1"):
            st.session_state["twelve_api_key_1"] = str(entered_key_1 or "").strip()
            st.session_state["twelve_api_key"] = str(entered_key_1 or "").strip()
            st.session_state["TWELVE_DATA_API_KEY"] = str(entered_key_1 or "").strip()
        if str(entered_key_2 or "").strip() or not st.session_state.get("twelve_api_key_2"):
            st.session_state["twelve_api_key_2"] = str(entered_key_2 or "").strip()
            st.session_state["TWELVE_DATA_API_KEY_2"] = str(entered_key_2 or "").strip()
    if connector_mode in ["doo_bridge", "fallback"] and show_secret_inputs:
        st.session_state.doo_bridge_url = st.text_input(
            "Doo Bridge URL",
            value=st.session_state.get("doo_bridge_url", ""),
            key=f"{key_prefix}_doo_bridge_url_v1",
            placeholder="http://127.0.0.1:8000/candles",
        )
        st.session_state.doo_bridge_token = st.text_input(
            "Doo Bridge token optional",
            value=st.session_state.get("doo_bridge_token", ""),
            type="password",
            key=f"{key_prefix}_doo_bridge_token_v1",
        )
    if not show_secret_inputs and connector_mode in ["twelve_pool", "twelve", "fallback"]:
        try:
            from core.secure_api_startup_20260619 import secure_secret_status
            key_status = secure_secret_status(st.session_state)
            key_ready = bool(key_status.get("twelve_key_1_configured") or key_status.get("twelve_key_2_configured") or key_status.get("second_api_configured"))
            key_source = str(key_status.get("twelve_key_1_source") or key_status.get("second_api_source") or "Not configured")
        except Exception:
            key_ready = bool(str(st.session_state.get("twelve_api_key_1", st.session_state.get("twelve_api_key", "")) or "").strip() or str(st.session_state.get("twelve_api_key_2", "") or "").strip())
            key_source = "Session replacement" if key_ready else "Not configured"
        st.info(
            f"Twelve Data key pool: configured ({key_source})."
            if key_ready
            else "Twelve Data key pool is not configured. Add Key 1/Key 2 in Streamlit Secrets or paste keys in Settings."
        )
    if not show_secret_inputs and connector_mode in ["doo_bridge", "fallback"]:
        st.caption("Doo Bridge URL/token remain available in the app drawer connector. Settings restores the requested Twelve Data and MT5 controls without duplicating secret fields.")

    if connector_mode == "safe_demo":
        st.session_state.allow_safe_demo = True
        st.warning("SAFE_DEMO is only for UI testing, not live trading decisions.")
    else:
        st.session_state.allow_safe_demo = st.checkbox(
            "Allow SAFE_DEMO fallback when real data fails",
            value=bool(st.session_state.get("allow_safe_demo", False)),
            key=f"{key_prefix}_allow_safe_demo_v1",
        )

    try:
        from core.connector_state_machine_20260621 import snapshot
        persistent = snapshot(st.session_state, "market_connector_20260621")
    except Exception:
        persistent = {"state": "CONNECTED" if st.session_state.get("connected") else "DISCONNECTED", "message": ""}
    c1, c2, c3 = st.columns(3)
    c1.button(
        "✅ Connect Once Using Saved Settings", key=f"{key_prefix}_connect_api_v1", use_container_width=True,
        on_click=_market_connect_callback, args=(key_prefix,), disabled=persistent.get("state") == "CONNECTING",
        help="Connects the saved main-symbol profile once. An identical connected profile is reused without another API request.",
    )
    c2.button(
        "🔄 Refresh Main Feed", key=f"{key_prefix}_refresh_api_v2", use_container_width=True,
        on_click=_market_refresh_callback, args=(key_prefix,), disabled=persistent.get("state") == "CONNECTING",
        help="Forces one new download for the Settings main symbol.",
    )
    c3.button(
        "⛔ Disconnect", key=f"{key_prefix}_disconnect_api_v1", use_container_width=True,
        on_click=_market_disconnect_callback, disabled=persistent.get("state") == "CONNECTING",
    )
    state_col, message_col = st.columns(2)
    state_col.metric("Connection State", str(persistent.get("state", "DISCONNECTED")))
    message_col.caption(str(persistent.get("message") or "Enter settings and press once to connect."))
    provider_cols = st.columns(3)
    preferred_provider, fallback_provider, _provider_route = _provider_route_labels(connector_mode)
    st.session_state["active_market_provider_20260705"] = preferred_provider
    st.session_state["fallback_market_provider_20260705"] = fallback_provider
    provider_cols[0].metric("Preferred Provider", preferred_provider)
    provider_cols[1].metric("Fallback Provider", fallback_provider)
    provider_cols[2].metric("Actual Candle Provider", str(st.session_state.get("actual_market_provider_used_20260708") or "NONE"))
    fallback_reason = str(st.session_state.get("market_provider_fallback_reason_20260708") or "")
    if fallback_reason:
        st.caption(f"Fallback Reason: {fallback_reason}")
    provenance = st.session_state.get("active_symbol_market_provenance_20260705")
    if isinstance(provenance, dict):
        actual_provider = str(provenance.get("provider") or "NONE").upper()
        attempts_raw = provenance.get("attempts")
        attempts = list(attempts_raw) if isinstance(attempts_raw, Sequence) and not isinstance(attempts_raw, (str, bytes, bytearray)) else []
        st.caption(
            f"Candle route result: {actual_provider} · "
            f"{int(st.session_state.get('last_connection_rows') or 0):,} validated row(s)."
        )
        failed_attempts = [item for item in attempts if not bool(item.get("ok"))]
        if failed_attempts:
            with st.expander("Open / Close — Why a provider was skipped or failed", expanded=False):
                for item in failed_attempts:
                    provider = str(item.get("provider") or "UNKNOWN").replace("_", " ").title()
                    category = str(item.get("category") or "FAILED")
                    detail = str(item.get("message") or "No detail returned")[:220]
                    st.caption(f"{provider} — {category}: {detail}")
    saved_profile = st.session_state.get("market_connector_saved_profile_20260702")
    if isinstance(saved_profile, dict):
        st.caption(
            "Saved profile: "
            f"{saved_profile.get('mode', '-')} · {saved_profile.get('main_symbol', '-')} / "
            f"{saved_profile.get('timeframe', '-')} · {int(saved_profile.get('bars') or 0):,} bars · "
            f"{len(saved_profile.get('selected_symbols') or [])} selected symbol(s). No secret values are stored in this profile."
        )

    try:
        rows = len(st.session_state.get("last_df")) if st.session_state.get("last_df") is not None else 0
    except Exception:
        rows = 0
    source = str(st.session_state.get("source", "DISCONNECTED") or "DISCONNECTED")
    m1, m2, m3 = st.columns(3)
    m1.metric("Market API", source)
    m2.metric("Symbol / TF", f"{st.session_state.get('symbol','EURUSD')} / {st.session_state.get('timeframe','H4')}")
    m3.metric("Loaded Rows", f"{rows:,}")

    st.markdown("##### Finnhub Credential and Candle Capability")
    st.caption("A Finnhub key can be valid for news/symbol endpoints while its candle endpoint is restricted by the account plan. These are shown separately.")
    try:
        from core.finnhub_connector import connection_status
        status = connection_status()
        f1, f2, f3 = st.columns(3)
        f1.metric("Credential", "VALID" if status.get("connected") else "NOT VALIDATED")
        f2.metric("News API", status.get("availability", "UNKNOWN"))
        f3.metric("Candle Feed", "WORKING" if st.session_state.get("finnhub_data_connected") else "FALLBACK USED / UNAVAILABLE")
        candle_message = str(st.session_state.get("finnhub_data_last_message") or "Not tested for the selected symbol/timeframe.")
        st.caption(f"Finnhub candle result: {candle_message[:240]}")
        st.caption(f"Last credential/news success: {status.get('last_success', 'Never')}")
    except Exception:
        st.info("Finnhub connector status is unavailable; the rest of the application remains usable.")
    if st.button("Finnhub key is managed in the Settings Finnhub section", key=f"{key_prefix}_finnhub_settings_owner_20260618", use_container_width=True, disabled=True):
        pass


def _render_timer(*, key_prefix: str = "main_drawer") -> None:
    st.markdown("#### ⏱ Trade Timer / Sound Alert")
    st.session_state.setdefault("sidebar_timer_minutes", int(st.session_state.get("timer_minutes", 120) or 120))
    st.session_state.setdefault("sidebar_timer_end", 0.0)
    st.session_state.setdefault("sidebar_timer_alerted", False)

    mins = st.number_input(
        "Timer minutes",
        min_value=1,
        max_value=1440,
        value=int(st.session_state.get("sidebar_timer_minutes", 120) or 120),
        step=5,
        key=f"{key_prefix}_timer_minutes_input_v1",
    )
    st.session_state.sidebar_timer_minutes = int(mins)

    try:
        import streamlit.components.v1 as components
        components.html(
            """
<button id="unlockMainDrawerTimerSound" style="width:100%;min-height:38px;border-radius:999px;border:1px solid #93c5fd;background:#eff6ff;font-weight:900;cursor:pointer;">🔊 Enable Timer Sound</button>
<div id="unlockMainDrawerTimerStatus" style="font-size:11px;text-align:center;margin-top:4px;color:#075985;">Tap once on phone/Cloud so alarm sound can play.</div>
<script>
(function(){
  const btn=document.getElementById('unlockMainDrawerTimerSound');
  const status=document.getElementById('unlockMainDrawerTimerStatus');
  async function unlock(){
    try{
      const AudioCtx=window.AudioContext||window.webkitAudioContext;
      const ctx=new AudioCtx(); const osc=ctx.createOscillator(); const gain=ctx.createGain();
      osc.frequency.value=660; gain.gain.value=0.001; osc.connect(gain); gain.connect(ctx.destination);
      osc.start(); osc.stop(ctx.currentTime+0.04); localStorage.setItem('m1_adx_timer_sound_unlocked','yes');
      status.textContent='Sound unlocked. Timer alarm can play on this browser.'; setTimeout(()=>ctx.close&&ctx.close(),120);
    }catch(e){status.textContent='Browser blocked sound. Keep page active and tap Start again.';}
  }
  btn.addEventListener('click', unlock);
  btn.addEventListener('touchend', function(e){e.preventDefault(); unlock();}, {passive:false});
})();
</script>
""",
            height=78,
        )
    except Exception:
        pass

    t1, t2 = st.columns(2)
    with t1:
        if st.button("▶ Start Timer", key=f"{key_prefix}_timer_start_v1", use_container_width=True):
            st.session_state.sidebar_timer_end = time.time() + int(mins) * 60
            st.session_state.sidebar_timer_alerted = False
            _safe_log_event(f"Main drawer timer started: {int(mins)} minutes")
            request_close_native_sidebar()
            _safe_rerun()
    with t2:
        if st.button("■ Reset Timer", key=f"{key_prefix}_timer_reset_v1", use_container_width=True):
            st.session_state.sidebar_timer_end = 0.0
            st.session_state.sidebar_timer_alerted = False
            _safe_log_event("Main drawer timer reset")
            _safe_rerun()

    end = float(st.session_state.get("sidebar_timer_end", 0) or 0)
    now = time.time()
    active = end > now
    remaining = max(0, int(end - now)) if end else 0
    status = "RUNNING" if active else ("TIME UP" if end else "STOPPED")
    st.markdown(
        f"""
<div class="new7-card">
  <b>Status:</b> {status}<br>
  <div style="font-size:1.55rem;font-weight:950;letter-spacing:.04em;">{_fmt_timer(remaining)}</div>
  <span style="font-size:.76rem;color:#64748b;">Timer state is shared with the native sidebar.</span>
</div>
""",
        unsafe_allow_html=True,
    )

    if end:
        try:
            import streamlit.components.v1 as components
            alarm_id = f"main_drawer_trade_timer_alarm_{int(end)}"
            components.html(
                f"""
<div style="font-family:Arial,sans-serif;padding:8px 10px;border-radius:14px;background:#eef6ff;border:1px solid #bfdbfe;color:#0f172a;text-align:center;">
  <div style="font-size:12px;font-weight:900;letter-spacing:.04em;">LIVE TIMER</div>
  <div id="mainDrawerLiveTimer" style="font-size:24px;font-weight:950;margin-top:3px;">--:--:--</div>
  <div id="mainDrawerLiveTimerStatus" style="font-size:12px;margin-top:2px;">syncing...</div>
</div>
<script>
(function() {{
  const endMs = {float(end) * 1000:.0f};
  const alarmKey = "{alarm_id}";
  const timerEl = document.getElementById("mainDrawerLiveTimer");
  const statusEl = document.getElementById("mainDrawerLiveTimerStatus");
  function pad(n) {{ return String(n).padStart(2, "0"); }}
  function fmt(sec) {{ sec=Math.max(0,Math.floor(sec)); const h=Math.floor(sec/3600); const m=Math.floor((sec%3600)/60); const s=sec%60; return pad(h)+":"+pad(m)+":"+pad(s); }}
  async function alarm() {{
    if(localStorage.getItem(alarmKey)==='played') return;
    localStorage.setItem(alarmKey,'played'); statusEl.textContent='TIME UP — alarm playing';
    try {{ if(navigator.vibrate) navigator.vibrate([700,220,700,220,1000]); }} catch(e) {{}}
    try {{
      const AudioCtx=window.AudioContext||window.webkitAudioContext; const ctx=new AudioCtx(); const stopAt=Date.now()+8000;
      async function beep(freq,len) {{ const osc=ctx.createOscillator(); const gain=ctx.createGain(); osc.type='square'; osc.frequency.value=freq; gain.gain.setValueAtTime(0.0001,ctx.currentTime); gain.gain.exponentialRampToValueAtTime(0.25,ctx.currentTime+0.02); gain.gain.exponentialRampToValueAtTime(0.0001,ctx.currentTime+len/1000); osc.connect(gain); gain.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime+len/1000+0.03); await new Promise(r=>setTimeout(r,len+100)); }}
      while(Date.now()<stopAt) {{ await beep(880,250); await beep(1320,250); }} setTimeout(()=>ctx.close&&ctx.close(),500);
    }} catch(e) {{}}
  }}
  function tick() {{ const rem=(endMs-Date.now())/1000; timerEl.textContent=fmt(rem); if(rem<=0){{statusEl.textContent='TIME UP'; alarm();}} else if(rem<=60){{statusEl.textContent='FINAL 1 MIN';}} else {{statusEl.textContent='running';}} }}
  tick(); setInterval(tick,1000);
}})();
</script>
""",
                height=96,
            )
        except Exception:
            pass

    if end and end <= now and not bool(st.session_state.get("sidebar_timer_alerted", False)):
        st.session_state.sidebar_timer_alerted = True
        st.warning("⏱ Timer reached 0. Check your trade / exit plan now.")


def _render_ui_and_account(*, key_prefix: str = "main_drawer") -> None:
    st.markdown("#### 👤 Account")
    # Phone/Laptop controls intentionally live only inside the floating/sidebar
    # menu, preventing duplicate UI mode buttons in Settings and Profile.
    mode = "Phone" if bool(st.session_state.get("phone_mode", False)) else "Laptop"
    st.metric("Display Mode", mode, "Change from ⋮ Menu")
    user = st.session_state.get("new7_auth_email", "Guest") or "Guest"
    st.caption(f"Signed in: {user} | " + ("Guest mode" if st.session_state.get("new7_auth_guest") else "Account mode"))
    if st.button("🚪 Logout", key=f"{key_prefix}_logout_v1", use_container_width=True):
        st.session_state["new7_auth_logged_in"] = False
        st.session_state["new7_auth_guest"] = False
        st.session_state["new7_auth_email"] = ""
        st.session_state["auth_mode"] = ""
        _safe_rerun()


def render_sidebar_fallback_panel(expanded: bool = False) -> None:
    """Render critical sidebar controls in the main page/drawer."""
    with st.expander("⚙️ Open / Close — Main-Page Sidebar Controls: API + Timer + UI + Account", expanded=expanded):
        st.caption("This is the no-fail replacement for the native sidebar. It uses separate widget keys, so Home/Lunch and native sidebar do not conflict.")
        _render_connector()
        st.divider()
        _render_timer()
        st.divider()
        _render_ui_and_account()
