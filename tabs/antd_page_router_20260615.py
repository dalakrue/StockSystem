"""Final synchronized page router (updated 2026-06-17).

Only the selected top-level page and selected inner page are imported/rendered.
All renderers consume the canonical runtime adapter already created by runner.py;
none of them may trigger a second shared calculation during the same rerun.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol
from typing import Any
import pandas as pd
import streamlit as st
_LEGACY_SINGLE_RUN_BUTTON_CONTRACT = 'button(\n        "▶ Run Calculation + Open Lunch"'

def _safe_rerun() -> None:
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _save_and_connect_twelve_callback(widget_key: str | None=None) -> None:
    """Resolve, validate, persist status and load candles in one click."""
    from core.transaction_guard_v8_20260622 import begin_transaction, finish_transaction
    from core.connector_state_machine_20260621 import begin, fail, succeed
    from core.secure_api_startup_20260619 import resolve_api_key
    token = begin_transaction(st.session_state, 'api_save_connect', payload={'widget': widget_key or 'streamlit_secret'})
    if not token.get('accepted'):
        return
    final_status = 'FAILED'
    begin(st.session_state, 'market_connector_20260621')
    try:
        pasted = str(st.session_state.get(widget_key, '') or '').strip() if widget_key else ''
        if pasted:
            st.session_state['twelve_api_key'] = pasted
            st.session_state['twelve_api_key_source'] = 'explicit'
            try:
                from core.connectors.credential_vault import save_credential
                st.session_state['twelve_credential_persistence_20260705'] = save_credential('TWELVE_DATA', pasted)
            except Exception as vault_exc:
                st.session_state['twelve_credential_persistence_20260705'] = {'ok': False, 'status': type(vault_exc).__name__}
        key = resolve_api_key('second_api', st.session_state)
        if not key:
            message = 'Twelve Data API key is not configured. Add [api_keys] second_api in Streamlit Secrets or paste a key in this box.'
            st.session_state['twelve_data_connected'] = False
            st.session_state['twelve_data_last_message'] = message
            fail(st.session_state, 'market_connector_20260621', message)
            return
        current_mode = str(st.session_state.get('connector_mode') or 'twelve').strip().lower()
        if current_mode not in {'twelve_pool', 'twelve', 'fallback'}:
            current_mode = 'twelve_pool'
        st.session_state['connector_mode'] = current_mode
        from core.data.market_data_orchestrator import MarketDataOrchestrator, provider_priority_for_state
        from core.runtime_selection_20260705 import normalize_symbol, normalize_timeframe
        selected = list(st.session_state.get('multi_symbol_selected_20260701') or [])
        symbol = normalize_symbol(st.session_state.get('multi_symbol_main_symbol_20260702') or (selected[0] if selected else st.session_state.get('symbol') or 'EURUSD'))
        timeframe = normalize_timeframe(st.session_state.get('timeframe') or 'H4')
        validation_state = dict(st.session_state)
        validation_state['market_data_provider_order_override_20260708'] = tuple(provider_priority_for_state(validation_state))
        result = MarketDataOrchestrator().fetch(symbol=symbol, timeframe=timeframe, state=validation_state, bars=min(5000, max(220, int(st.session_state.get('connector_bars', 600) or 600))), run_id='CONNECT-VALIDATION', force_live=True, essential=True)
        outcome = result.to_dict(include_frame=False)
        attempts = list(result.attempts or [])
        twelve_attempt = next((item for item in attempts if str(item.get('provider') or '').upper() in {'TWELVE_DATA_KEY_POOL', 'TWELVE_DATA_FALLBACK', 'TWELVE_DATA'}), {})
        twelve_connected = bool(twelve_attempt.get('ok'))
        twelve_message = str(twelve_attempt.get('message') or '') or (str(result.message) if twelve_connected else str(twelve_attempt.get('category') or result.message))
        if isinstance(result.frame, pd.DataFrame) and (not result.frame.empty):
            legacy = result.frame.copy()
            if 'open_time' in legacy.columns:
                legacy['time'] = pd.to_datetime(legacy['open_time'], errors='coerce', utc=True)
            keep = [column for column in ('time', 'open', 'high', 'low', 'close', 'volume') if column in legacy.columns]
            if keep:
                st.session_state['last_df'] = legacy.loc[:, keep].copy()
                st.session_state['last_connection_rows'] = int(len(legacy))
            st.session_state['source'] = str(result.provider or 'UNKNOWN')
            st.session_state['connected'] = bool(result.ok)
            set_legacy_calculation_symbol(st.session_state, symbol, connector=True)
            st.session_state['timeframe'] = timeframe
        st.session_state['twelve_one_click_connect_result_20260628'] = outcome
        st.session_state['twelve_data_connected'] = twelve_connected
        st.session_state['twelve_data_last_message'] = twelve_message
        st.session_state['twelve_data_last_checked_at'] = pd.Timestamp.now(tz='UTC').isoformat()
        provider_route = tuple(provider_priority_for_state(validation_state))
        preferred_provider = str(provider_route[0] if provider_route else 'TWELVE_DATA_KEY_POOL')
        fallback_provider = str(provider_route[1] if len(provider_route) > 1 else 'LOCAL_VALID_CACHE')
        if twelve_connected:
            st.session_state['twelve_data_last_success_at'] = st.session_state['twelve_data_last_checked_at']
            st.session_state['active_market_provider_20260705'] = preferred_provider
            st.session_state['fallback_market_provider_20260705'] = fallback_provider
            st.session_state['market_data_provider_order_override_20260708'] = provider_route
            st.session_state['actual_market_provider_used_20260708'] = 'TWELVE_DATA_KEY_POOL'
            succeed(st.session_state, 'market_connector_20260621', f'Twelve Data connected: {symbol} {timeframe}, {len(result.frame):,} validated candles.')
            final_status = 'CONNECTED'
        elif result.ok:
            st.session_state['active_market_provider_20260705'] = preferred_provider
            st.session_state['fallback_market_provider_20260705'] = fallback_provider
            st.session_state['market_data_provider_order_override_20260708'] = provider_route
            st.session_state['actual_market_provider_used_20260708'] = str(result.provider or 'LOCAL_VALID_CACHE')
            succeed(st.session_state, 'market_connector_20260621', f'Market data loaded through {result.provider}; Twelve Data failed: {twelve_message}')
            final_status = 'FALLBACK_CONNECTED'
        else:
            fail(st.session_state, 'market_connector_20260621', f'Twelve Data connection failed: {twelve_message}')
        try:
            from core.connectors.credential_vault import mark_connection
            mark_connection('TWELVE_DATA', connected=twelve_connected, configured=bool(key), status='VALIDATED' if twelve_connected else str(twelve_attempt.get('category') or 'VALIDATION_FAILED'), error_code='' if twelve_connected else str(twelve_attempt.get('category') or 'VALIDATION_FAILED'))
        except Exception:
            pass
    except Exception as exc:
        message = f'Twelve Data connection failed safely: {type(exc).__name__}: {str(exc)[:180]}'
        st.session_state['twelve_data_connected'] = False
        st.session_state['twelve_data_last_message'] = message
        fail(st.session_state, 'market_connector_20260621', message)
    finally:
        finish_transaction(st.session_state, 'api_save_connect', token=str(token.get('token') or ''), status=final_status)

def _render_mobile_api_key_center() -> None:
    """One Twelve Data control for pasted keys and Streamlit Secrets."""
    st.markdown('\n    <style>\n    @media (max-width: 780px) {\n      div[data-testid="stTextInput"] input,\n      div[data-testid="stTextArea"] textarea {\n        font-size: 16px !important; min-height: 48px !important;\n        -webkit-user-select: text !important; user-select: text !important;\n        -webkit-touch-callout: default !important; touch-action: manipulation !important;\n      }\n      div[data-testid="stTextArea"] textarea {min-height: 76px !important; overflow-wrap: anywhere !important;}\n      div[data-testid="stButton"] button {min-height: 46px !important; white-space: normal !important;}\n    }\n    </style>\n    ', unsafe_allow_html=True)
    st.markdown('### 🔑 Secure API Key Connection')
    from core.secure_api_startup_20260619 import secure_secret_status
    secret_state = secure_secret_status(st.session_state)
    persisted = {}
    try:
        from core.connectors.credential_vault import status as credential_status
        persisted = next((row for row in credential_status() if str(row.get('provider') or '').upper() == 'TWELVE_DATA'), {})
    except Exception:
        persisted = {}
    configured = bool(secret_state.get('second_api_configured'))
    connected = bool(st.session_state.get('twelve_data_connected') or (persisted.get('connected') and st.session_state.get('connected') and (str(st.session_state.get('source') or '').upper() == 'TWELVE_DATA')))
    try:
        loaded_rows = len(st.session_state.get('last_df')) if st.session_state.get('last_df') is not None else 0
    except Exception:
        loaded_rows = 0
    status_cols = st.columns(4)
    status_cols[0].metric('Twelve Key', 'CONFIGURED' if configured else 'NOT CONFIGURED')
    status_cols[1].metric('Twelve Connection', 'CONNECTED' if connected else 'NOT CONNECTED')
    status_cols[2].metric('Candle Rows', f'{loaded_rows:,}')
    status_cols[3].metric('Credential Source', str(secret_state.get('second_api_source') or 'Not configured')[:28])
    last_message = str(st.session_state.get('twelve_data_last_message') or persisted.get('last_status') or 'Press connect once. A pasted key overrides an older Streamlit Secret.')
    st.caption(last_message)
    st.caption('Accepted Streamlit Secret: [api_keys] second_api = "...". Common aliases such as TWELVE_DATA_API_KEY and [twelve_data] api_key are also supported.')
    twelve_generation = int(st.session_state.get('settings_mobile_twelve_generation_20260619', 0) or 0)
    widget_key = f'settings_mobile_twelve_api_key_paste_20260619_{twelve_generation}'
    with st.expander('Open / Close — Twelve Data API Key + Connection', expanded=True):
        value = st.text_area('Twelve Data API key — optional replacement', value='', key=widget_key, height=76, placeholder='Leave blank to use Streamlit Secrets, or paste a replacement key', help='The stored server-side secret is never autofilled into this browser field.')
        c1, c2 = st.columns(2)
        c1.button('Connect Twelve Data + Load Candles', key='settings_mobile_save_twelve_20260619', use_container_width=True, on_click=_save_and_connect_twelve_callback, args=(widget_key,), help='Uses the pasted key when present; otherwise uses Streamlit Secrets or encrypted saved state.')
        if c2.button('Clear Pasted Replacement', key='settings_mobile_clear_twelve_20260619', use_container_width=True):
            st.session_state['twelve_api_key'] = ''
            st.session_state.pop('twelve_api_key_source', None)
            st.session_state['settings_mobile_twelve_generation_20260619'] = twelve_generation + 1
            st.success('The browser replacement was cleared. Streamlit Secrets and encrypted saved credentials remain available.')
            _safe_rerun()

def _render_market_time_metrics(*, query_mt5: bool=True) -> dict[str, Any]:
    """Show feed freshness without starting a calculation."""
    try:
        from core.market_time_freshness_20260622 import market_time_snapshot
        snap = market_time_snapshot(st.session_state, query_mt5=query_mt5)
    except Exception as exc:
        snap = {'status': 'CHECK', 'current_utc_display': 'Unavailable', 'broker_clock_display': 'Unavailable', 'latest_loaded_display': 'Unavailable', 'lag_minutes': None, 'source': 'UNKNOWN', 'error': str(exc)}
    cols = st.columns(5)
    cols[0].metric('Feed Freshness', str(snap.get('status') or 'CHECK'), str(snap.get('source') or 'DISCONNECTED'))
    cols[1].metric('Current UTC', str(snap.get('current_utc_display') or '-').replace(' UTC', ''))
    cols[2].metric('MT5 Latest Tick', str(snap.get('mt5_tick_display') or 'Not available').replace(' UTC', ''))
    cols[3].metric('Broker Clock', str(snap.get('broker_clock_display') or 'Not available'))
    lag = snap.get('lag_minutes')
    has_loaded_candle = bool(snap.get('latest_loaded_broker_display'))
    delta = f'{lag:g} min behind current bar' if isinstance(lag, (int, float)) else 'Waiting for connected data'
    latest_display = str(snap.get('latest_loaded_broker_display') or 'Not available yet')
    cols[4].metric('Latest Candle — Broker', latest_display, delta, delta_color='off' if not has_loaded_candle else 'normal')
    st.caption('MetaTrader tick timestamps are normalized to UTC for calculations. Visible candle time uses the configured broker offset; Myanmar time remains a separate UTC+6:30 display.')
    return snap

def _render_market_connector_section(*, include_multi_symbol_controls: bool=False, foreground_container: Any | None=None, load_progress_container: Any | None=None):
    with st.container(border=True):
        st.markdown('### 🔌 API Source Connector Panel')
        st.caption('Foreground symbol router: cache first, then Twelve Data key pool, then Finnhub candle fallback, then last-known valid cache. API connection success is separated from candle-data success.')
        provider_choice_options = ['AUTO_SYMBOL_ROUTER', 'TWELVE_DATA_KEY_POOL']
        current_choice = str(st.session_state.get('foreground_main_provider_choice_20260708') or 'AUTO_SYMBOL_ROUTER')
        if current_choice not in provider_choice_options:
            current_choice = 'AUTO_SYMBOL_ROUTER'
        selected_choice = st.selectbox('Main Provider Choice', provider_choice_options, index=provider_choice_options.index(current_choice), key='foreground_main_provider_choice_20260708', help='AUTO_SYMBOL_ROUTER keeps local cache first and Twelve Data key pool as the first live candle API.')
        st.session_state['connector_mode'] = 'twelve_pool'
        active_provider = str(st.session_state.get('active_market_provider_20260705') or 'TWELVE_DATA_KEY_POOL')
        fallback_provider = str(st.session_state.get('fallback_market_provider_20260705') or 'FINNHUB / LOCAL_CACHE')
        p1, p2, p3 = st.columns(3)
        p1.metric('Selected Router Mode', selected_choice)
        p2.metric('First Live Candle API', 'TWELVE_DATA_KEY_POOL')
        p3.metric('Fallback Provider', fallback_provider)
        st.number_input('MT5 broker chart UTC offset (display only)', min_value=-12.0, max_value=14.0, step=0.5, key='mt5_broker_utc_offset_hours_20260622', help='MT5 Python tick timestamps are UTC. Set the exact broker-chart offset. All Lunch Date/Weekday/Hour columns are rebuilt from this same broker clock.')
        _render_twelve_key_pool_section()
        try:
            from ui.sidebar_fallback_panel import _render_connector
            _render_connector(key_prefix='settings_market_20260619', show_secret_inputs=False, show_symbol_selector=False)
        except Exception as exc:
            try:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error('settings.market_connector', exc)
            except Exception:
                incident = 'connector-render'
            st.warning(f'The advanced connection panel could not load. The safe connection controls remain available. Support reference: {incident}.')
            source_options = ['twelve_pool', 'twelve', 'fallback', 'safe_demo']
            current_source = str(st.session_state.get('connector_mode') or 'twelve_pool')
            if current_source in {'finnhub', 'mt5', 'doo_bridge'}:
                current_source = 'twelve_pool'
            if current_source not in source_options:
                current_source = 'twelve_pool'
            st.session_state['connector_mode'] = st.selectbox('API source', source_options, index=source_options.index(current_source), key='settings_market_emergency_source_20260702')
            selected = st.session_state.get('multi_symbol_selected_20260701') or []
            symbol = str(selected[0] if selected else st.session_state.get('multi_symbol_main_symbol_20260702') or st.session_state.get('symbol') or 'XAUUSD').strip().upper().replace('/', '').replace(' ', '')
            set_legacy_calculation_symbol(st.session_state, symbol, connector=True)
            st.caption(f'Emergency connector uses Main Core Symbol: {symbol}')
            timeframe_options = ['M1', 'M2', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'CUSTOM']
            current_tf = str(st.session_state.get('timeframe') or 'H1').upper()
            if current_tf not in timeframe_options:
                current_tf = 'H1'
            st.session_state['timeframe'] = st.selectbox('Timeframe', timeframe_options, index=timeframe_options.index(current_tf), key='settings_market_emergency_timeframe_20260702')
            st.session_state['connector_bars'] = int(st.number_input('Candles / bars', min_value=100, max_value=5000, value=min(5000, max(220, int(st.session_state.get('connector_bars', 600) or 600))), step=100, key='settings_market_emergency_bars_20260702'))
            st.warning('The visible emergency connector is active. Fix the renderer error above for one-click connection, but symbol/timeframe/candle setup remains available.')
        if include_multi_symbol_controls:
            from ui.multi_symbol_settings_20260701 import render_multi_symbol_selectors, render_calculation_mode_selector
            groups = render_multi_symbol_selectors(st.session_state, foreground_container=foreground_container, load_progress_container=load_progress_container)
            scope = render_calculation_mode_selector(st.session_state)
            return (groups, scope)
    return None

def _render_twelve_key_pool_section() -> None:
    """Settings-tab Twelve Data multi-key pool connector."""
    with st.container(border=True):
        st.markdown('#### Twelve Data Key Pool')
        st.caption('Use two different Twelve Data API keys safely. Each key has its own minute credit counter, cooldown, 429 handling, and masked status.')
        try:
            from core.secure_api_startup_20260619 import resolve_api_key
            resolved_key_1 = str(resolve_api_key('second_api', st.session_state) or '').strip()
            resolved_key_2 = str(resolve_api_key('twelve_key_2', st.session_state) or '').strip()
        except Exception:
            resolved_key_1 = ''
            resolved_key_2 = ''
        existing_key_1 = str(st.session_state.get('twelve_api_key_1') or st.session_state.get('twelve_api_key') or st.session_state.get('TWELVE_DATA_API_KEY') or resolved_key_1 or '')
        existing_key_2 = str(st.session_state.get('twelve_api_key_2') or st.session_state.get('TWELVE_DATA_API_KEY_2') or resolved_key_2 or '')
        key1 = st.text_input('Twelve Data API Key 1', value=existing_key_1, type='password', key='settings_twelve_data_api_key_1_20260708')
        key2 = st.text_input('Twelve Data API Key 2', value=existing_key_2, type='password', key='settings_twelve_data_api_key_2_20260708')
        st.session_state['enable_twelve_multi_key_loading'] = st.checkbox('Enable Multi-Key Loading', value=bool(st.session_state.get('enable_twelve_multi_key_loading', True)), key='settings_enable_twelve_multi_key_loading_20260708')
        if key1:
            st.session_state['twelve_api_key_1'] = key1.strip()
            st.session_state['twelve_api_key'] = key1.strip()
            st.session_state['TWELVE_DATA_API_KEY'] = key1.strip()
        if key2:
            st.session_state['twelve_api_key_2'] = key2.strip()
            st.session_state['TWELVE_DATA_API_KEY_2'] = key2.strip()
        save_col, test1_col, test2_col = st.columns(3)
        if save_col.button('Save Twelve Keys', key='save_twelve_key_pool_20260708', use_container_width=True):
            try:
                from core.connectors.credential_vault import save_credential
                saved_1 = save_credential('TWELVE_DATA_KEY_1', st.session_state.get('twelve_api_key_1') or st.session_state.get('twelve_api_key') or '')
                save_credential('TWELVE_DATA', st.session_state.get('twelve_api_key_1') or st.session_state.get('twelve_api_key') or '')
                saved_2 = save_credential('TWELVE_DATA_KEY_2', st.session_state.get('twelve_api_key_2') or '')
                st.success(f"Keys saved. Key 1: {saved_1.get('status', saved_1.get('ok'))}; Key 2: {saved_2.get('status', saved_2.get('ok'))}")
            except Exception as exc:
                st.error(f'Twelve key save failed: {type(exc).__name__}: {exc}')
        if test1_col.button('Test Key 1', key='test_twelve_key_1_20260708', use_container_width=True):
            try:
                from core.twelve_data_key_pool import test_twelve_data_key
                st.session_state['twelve_key_1_connection_test_20260708'] = test_twelve_data_key(st.session_state, alias='TWELVE_KEY_1')
            except Exception as exc:
                st.session_state['twelve_key_1_connection_test_20260708'] = {'connected': False, 'status': 'FAILED', 'error_message': f'{type(exc).__name__}: {exc}'}
        if test2_col.button('Test Key 2', key='test_twelve_key_2_20260708', use_container_width=True):
            try:
                from core.twelve_data_key_pool import test_twelve_data_key
                st.session_state['twelve_key_2_connection_test_20260708'] = test_twelve_data_key(st.session_state, alias='TWELVE_KEY_2')
            except Exception as exc:
                st.session_state['twelve_key_2_connection_test_20260708'] = {'connected': False, 'status': 'FAILED', 'error_message': f'{type(exc).__name__}: {exc}'}
        try:
            from core.twelve_data_key_pool import TwelveDataKeyPool
            snapshot = TwelveDataKeyPool.from_state(st.session_state).status_snapshot()
            rows = []
            for alias, info in snapshot.items():
                test_key = 'twelve_key_1_connection_test_20260708' if alias.endswith('1') else 'twelve_key_2_connection_test_20260708'
                test_result = st.session_state.get(test_key) if isinstance(st.session_state.get(test_key), Mapping) else {}
                rows.append({'Key Alias': alias, 'Masked Key': info.get('masked_key'), 'Status': test_result.get('status') or ('CONNECTED' if info.get('connected') else 'CONFIGURED' if info.get('configured') else 'NOT_CONFIGURED'), 'Remaining Credits': info.get('remaining_credits'), 'Last Success': info.get('last_successful_request_time'), 'Last 429': info.get('last_429_time'), 'Cooldown Reset': info.get('cooldown_reset_time'), 'Failure Reason': test_result.get('error_message') or info.get('failure_reason') or ''})
            st.dataframe(rows, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.caption(f'Twelve key-pool status unavailable: {type(exc).__name__}: {exc}')
        try:
            from core.data.market_data_orchestrator import provider_priority_for_state
            provider_route = tuple(provider_priority_for_state(st.session_state))
        except Exception:
            provider_route = ('TWELVE_DATA_KEY_POOL', 'FINNHUB', 'LOCAL_VALID_CACHE')
        st.session_state.setdefault('connector_mode', 'twelve_pool')
        st.session_state['active_market_provider_20260705'] = str(provider_route[0] if provider_route else 'TWELVE_DATA_KEY_POOL')
        st.session_state['fallback_market_provider_20260705'] = str(provider_route[1] if len(provider_route) > 1 else 'LOCAL_VALID_CACHE')
        st.session_state['market_data_provider_order_override_20260708'] = provider_route

def _render_finnhub_connector_section() -> None:
    with st.container(border=True):
        st.markdown('### 📰 Finnhub Connector — Always Visible')
        try:
            from core.finnhub_connector import render_finnhub_connector
            render_finnhub_connector(location='settings')
        except Exception as exc:
            try:
                from core.complete_repair_20260705 import log_internal_error
                incident = log_internal_error('settings.finnhub_connector', exc)
            except Exception:
                incident = 'finnhub-render'
            st.warning(f'Finnhub status could not be loaded. Twelve Data and persisted fallbacks remain available. Support reference: {incident}.')
            st.caption('The Finnhub section remains visible. Add the key in Streamlit Secrets; no secret is printed in this interface.')

def _render_settings() -> None:
    st.session_state.setdefault('mt5_broker_utc_offset_hours_20260622', 4.0)
    if not st.session_state.get('twelve_key_pool_migration_20260708'):
        st.session_state.setdefault('connector_mode', 'twelve_pool')
        try:
            from core.data.market_data_orchestrator import provider_priority_for_state
            provider_route = tuple(provider_priority_for_state(st.session_state))
        except Exception:
            provider_route = ('TWELVE_DATA_KEY_POOL', 'FINNHUB', 'LOCAL_VALID_CACHE')
        st.session_state['active_market_provider_20260705'] = str(provider_route[0] if provider_route else 'TWELVE_DATA_KEY_POOL')
        st.session_state['fallback_market_provider_20260705'] = str(provider_route[1] if len(provider_route) > 1 else 'LOCAL_VALID_CACHE')
        st.session_state['market_data_provider_order_override_20260708'] = provider_route
        st.session_state['twelve_key_pool_migration_20260708'] = True
    if not st.session_state.get('settings_h1_default_initialized_20260729'):
        _existing_tf_20260708 = str(st.session_state.get('settings_timeframe') or st.session_state.get('selected_timeframe') or st.session_state.get('timeframe') or 'H1').upper()
        if not _existing_tf_20260708 or _existing_tf_20260708 == 'H4' or st.session_state.get('settings_h4_default_initialized_20260707'):
            _existing_tf_20260708 = 'H1'
        st.session_state['timeframe'] = _existing_tf_20260708
        st.session_state['selected_timeframe'] = _existing_tf_20260708
        st.session_state['settings_timeframe'] = _existing_tf_20260708
        st.session_state['last_connected_timeframe'] = _existing_tf_20260708
        st.session_state['settings_market_20260619_timeframe_v1'] = _existing_tf_20260708
        st.session_state['settings_market_emergency_timeframe_20260702'] = _existing_tf_20260708
        st.session_state['settings_h1_default_initialized_20260729'] = True
    if not st.session_state.get('startup_top30_load_attempted_20260824'):
        st.session_state['startup_top30_load_attempted_20260824'] = True
        st.session_state['settings_top_load_all_requested_20260823'] = True
        st.session_state['settings_top_super_quick_requested_20260823'] = True
        st.session_state['startup_top30_load_status_20260824'] = 'QUEUED'
    st.markdown('### ⚙️ Settings')
    st.markdown('#### ⚡ Quick Actions')
    top_progress_slot_20260823 = st.empty()
    quick_action_cols = st.columns(2)
    top_load_all_clicked = quick_action_cols[0].button('📥 Load All Selected (Top 30)', key='settings_top_load_all_selected_20260823', use_container_width=True, help='Load the complete selected top-30 universe with the three selector workers.')
    top_super_quick_clicked = quick_action_cols[1].button('⚡ Super Quick Run', key='settings_top_super_quick_20260823', use_container_width=True, help='Run the bounded Field 3 calculation on already-loaded candles for an instant result.')
    top_load_progress_slot_20260824 = st.empty()
    if top_load_all_clicked:
        top_load_progress_slot_20260824.progress(0.0, text='0.0% — starting top-30 load…')
    if top_load_all_clicked:
        st.session_state['settings_top_load_all_requested_20260823'] = True
    if top_super_quick_clicked:
        st.session_state['settings_top_super_quick_requested_20260823'] = True
    try:
        from core.instant_run_engine_20260705 import current_job as _top_progress_job
        _top_job = _top_progress_job(st.session_state, restore=False)
        if isinstance(_top_job, Mapping):
            _top_percent = float(_top_job.get('progress_percent') or 0.0)
            _top_stage = str(_top_job.get('current_stage') or 'Queued')
            top_progress_slot_20260823.progress(max(0.0, min(1.0, _top_percent / 100.0)), text=f'{_top_percent:.1f}% — {_top_stage}')
    except Exception:
        pass
    foreground_loading_slot_20260823 = st.empty()
    try:
        from core.mobile_lite_mode_20260628 import render_mobile_mode_control
        with st.expander('Open / Close — Extreme Mobile Lite Mode', expanded=bool(st.session_state.get('phone_mode'))):
            render_mobile_mode_control(st, st.session_state, key='settings_mobile_lite_20260628')
            st.caption('Mobile Lite disables decorative UI, bounds tables and loads one field at a time. Calculation values remain identical.')
    except Exception as mobile_mode_exc:
        st.caption(f'Mobile Lite control unavailable: {mobile_mode_exc}')
    st.caption('Load symbols at the selected timeframe first, then press Super Quick Run Calculation.')
    _render_market_time_metrics(query_mt5=False)
    st.markdown('### Run Calculation Console — Top of Settings')
    try:
        connector_controls = _render_market_connector_section(include_multi_symbol_controls=True, foreground_container=foreground_loading_slot_20260823, load_progress_container=top_load_progress_slot_20260824)
        if not isinstance(connector_controls, tuple) or len(connector_controls) != 2:
            raise RuntimeError('The integrated connector did not return selector controls.')
        symbol_groups_20260706, selected_scope_20260701 = connector_controls
    except Exception as integrated_connector_exc:
        st.session_state['integrated_connector_controls_error_20260707'] = f'{type(integrated_connector_exc).__name__}: {integrated_connector_exc}'
        st.warning('The integrated connector panel used its safe selector fallback; calculations remain available.')
        from ui.multi_symbol_settings_20260701 import render_multi_symbol_selectors, render_calculation_mode_selector
        symbol_groups_20260706 = render_multi_symbol_selectors(st.session_state, foreground_container=foreground_loading_slot_20260823, load_progress_container=top_load_progress_slot_20260824)
        selected_scope_20260701 = render_calculation_mode_selector(st.session_state)
    try:
        from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
        from core.multi_symbol_run_groups_20260706 import CONFIGURED_UNION_KEY, save_group_preferences, union_symbols
        from core.runtime_selection_20260705 import save_runtime_preferences
        configured_union_20260706 = union_symbols(symbol_groups_20260706.get('FIRST') or [], symbol_groups_20260706.get('SECOND') or [], symbol_groups_20260706.get('THIRD') or [])
        st.session_state[CONFIGURED_UNION_KEY] = list(configured_union_20260706)
        try:
            from core.current_result_sync_20260708 import sync_settings_source_of_truth
            sync_settings_source_of_truth(st.session_state, configured_union_20260706 or ['EURUSD'], st.session_state.get('timeframe') or 'H1', reason='settings_configured_union')
        except Exception as current_sync_exc_20260708:
            st.session_state['current_result_sync_error_20260708'] = f'{type(current_sync_exc_20260708).__name__}: {current_sync_exc_20260708}'
        save_runtime_preferences(DEFAULT_DB_PATH, configured_union_20260706 or ['EURUSD'], st.session_state.get('timeframe') or 'H1')
        save_group_preferences(DEFAULT_DB_PATH, st.session_state)
    except Exception as runtime_sync_exc:
        configured_union_20260706 = []
        st.session_state['runtime_selection_sync_error_20260705'] = f'{type(runtime_sync_exc).__name__}: {runtime_sync_exc}'
    previous_status = st.session_state.get('settings_run_status_20260617')
    if isinstance(previous_status, Mapping):
        canonical_ok = bool((previous_status.get('canonical') or {}).get('ok'))
        previous_used = bool(st.session_state.get('settings_used_previous_canonical_20260622'))
        top = st.columns(3)
        top[0].metric('All-in-One Run', 'FULLY WORKED' if canonical_ok else 'PREVIOUS VALID USED' if previous_used else 'CHECK')
        top[1].metric('Published Generation', str(previous_status.get('calculation_generation', st.session_state.get('canonical_calculation_generation_20260617', '-'))))
        top[2].metric('Auto-Open Field 3', 'READY' if canonical_ok or previous_used else 'WAITING')
    st.caption('Select and load symbols above. Super Quick uses the validated loaded candles and publishes the compact result without the full research rebuild.')
    try:
        from core.instant_run_engine_20260705 import ACTIVE_STATUSES as _INSTANT_ACTIVE_STATUSES, current_job as _current_instant_job
        _instant_lock_job = _current_instant_job(st.session_state, restore=True)
        _instant_job_active = isinstance(_instant_lock_job, Mapping) and str(_instant_lock_job.get('status') or '').upper() in _INSTANT_ACTIVE_STATUSES
    except Exception:
        _instant_job_active = False
    if not _instant_job_active:
        for _lock_key in ('instant_run_engine_running_20260705', 'settings_one_click_running_20260624', 'multi_symbol_run_in_progress_20260701'):
            st.session_state[_lock_key] = False
    run_locked_20260624 = bool(_instant_job_active)
    first_group_20260706 = list(symbol_groups_20260706.get('FIRST') or [])
    second_group_20260706 = list(symbol_groups_20260706.get('SECOND') or [])
    third_group_20260706 = list(symbol_groups_20260706.get('THIRD') or [])
    timeframe_for_load_20260707 = str(st.session_state.get('timeframe') or st.session_state.get('selected_timeframe') or 'H1').upper()
    try:
        from core.multi_symbol_load_manager_20260707 import loaded_group_status
        first_load_status_20260707 = loaded_group_status(st.session_state, 'FIRST', first_group_20260706, timeframe_for_load_20260707)
        second_load_status_20260707 = loaded_group_status(st.session_state, 'SECOND', second_group_20260706, timeframe_for_load_20260707)
        third_load_status_20260707 = loaded_group_status(st.session_state, 'THIRD', third_group_20260706, timeframe_for_load_20260707)
    except Exception as load_status_exc_20260707:
        unavailable_status = {'ready': False, 'status': 'UNAVAILABLE', 'loaded_symbols': [], 'failed_symbols': [], 'message': f'Load manager unavailable: {type(load_status_exc_20260707).__name__}: {load_status_exc_20260707}'}
        first_load_status_20260707 = dict(unavailable_status)
        second_load_status_20260707 = dict(unavailable_status)
        third_load_status_20260707 = dict(unavailable_status)
    configured_groups_for_run_20260707 = {'FIRST': first_group_20260706, 'SECOND': second_group_20260706, 'THIRD': third_group_20260706}
    configured_count_20260707 = len(dict.fromkeys(first_group_20260706 + second_group_20260706 + third_group_20260706))
    try:
        from core.multi_symbol_load_manager_20260707 import loaded_universe_status
        cumulative_load_status_20260707 = loaded_universe_status(st.session_state, configured_groups_for_run_20260707, timeframe_for_load_20260707)
    except Exception as cumulative_exc_20260707:
        cumulative_load_status_20260707 = {'ready': False, 'loaded_symbols': [], 'message': f'Cumulative load status unavailable: {type(cumulative_exc_20260707).__name__}: {cumulative_exc_20260707}'}
    load_summary_cols = st.columns(4)
    for slot, title, status in ((load_summary_cols[0], 'Selector 1 Load', first_load_status_20260707), (load_summary_cols[1], 'Selector 2 Load', second_load_status_20260707), (load_summary_cols[2], 'Selector 3 Load', third_load_status_20260707)):
        loaded_count = len(status.get('loaded_symbols') or [])
        failed_count = len(status.get('failed_symbols') or [])
        slot.metric(title, f'{loaded_count} READY', delta=f'{failed_count} rejected' if failed_count else str(status.get('status') or 'NOT_LOADED'))
    cumulative_ready_count_20260727 = len(cumulative_load_status_20260707.get('loaded_symbols') or [])
    cumulative_failed_count_20260727 = max(0, configured_count_20260707 - cumulative_ready_count_20260727)
    load_summary_cols[3].metric('All Run Buttons', f'{cumulative_ready_count_20260727} READY', delta=f'{cumulative_failed_count_20260727} not ready' if cumulative_failed_count_20260727 else 'ALL LOADED')
    st.caption(f'The three left cards are load diagnostics only. Super Quick, Quick, and Full all calculate the same {cumulative_ready_count_20260727}-symbol loaded universe; the buttons differ only in calculation depth.')
    try:
        from core.canonical_symbol_selection_20260709 import render_selector as _render_global_loaded_selector
        _render_global_loaded_selector(st, st.session_state, surface='settings_global', title='Global Multi-Symbol Display Selector — Loaded Symbols Only', expanded=True)
    except Exception as global_selector_exc_20260722:
        st.session_state['settings_global_symbol_selector_error_20260722'] = f'{type(global_selector_exc_20260722).__name__}: {global_selector_exc_20260722}'
    st.caption(f"Cumulative calculation universe: {len(cumulative_load_status_20260707.get('loaded_symbols') or [])} loaded symbol(s). All three buttons calculate this same loaded universe; only calculation depth changes.")
    run_disabled_20260707 = not bool(cumulative_load_status_20260707.get('loaded_symbols'))
    super_requested_from_top = bool(st.session_state.pop('settings_top_super_quick_requested_20260823', False))
    super_clicked = bool(super_requested_from_top and (not run_disabled_20260707))
    if super_requested_from_top and run_disabled_20260707:
        st.warning('Super Quick needs at least one loaded symbol. Use Load All Selected first.')
    st.caption('Super Quick runs from the top Quick Actions control after validated candles are loaded.')
    quick_clicked = False
    full_clicked = False
    load_update_clicked = False
    run_clicked_20260701 = bool(quick_clicked or full_clicked or super_clicked)
    run_symbols_20260706: list[str] = []
    active_group_20260706 = 'SECOND'
    if super_clicked:
        selected_scope_20260701 = 'LUNCH_CORE'
        active_group_20260706 = 'FIRST'
    elif quick_clicked:
        selected_scope_20260701 = 'QUICK'
        active_group_20260706 = 'SECOND'
    elif full_clicked:
        selected_scope_20260701 = 'FULL'
        active_group_20260706 = 'THIRD'
    if run_clicked_20260701:
        run_symbols_20260706 = list(cumulative_load_status_20260707.get('loaded_symbols') or [])
    reset_col = st.columns([3, 1])[1]
    if run_clicked_20260701:
        st.session_state['settings_calculation_scope_20260625'] = selected_scope_20260701
        st.session_state['field3_fast_two_table_mode_20260722'] = selected_scope_20260701 == 'LUNCH_CORE'
        st.session_state['field3_last_run_scope_20260722'] = selected_scope_20260701
        try:
            from core.field10_fast_lane_20260709 import set_field10_fast_lane
            set_field10_fast_lane(st.session_state, enabled=selected_scope_20260701 == 'LUNCH_CORE', scope=selected_scope_20260701)
        except Exception as fast_lane_exc_20260709:
            st.session_state['field10_fast_lane_setup_error_20260709'] = f'{type(fast_lane_exc_20260709).__name__}: {fast_lane_exc_20260709}'
        configured_for_click = configured_groups_for_run_20260707.get(active_group_20260706, [])
        try:
            from core.multi_symbol_load_manager_20260707 import activate_loaded_universe_for_run
            activation_20260707 = activate_loaded_universe_for_run(st.session_state, selected_scope_20260701, configured_groups_for_run_20260707, timeframe_for_load_20260707)
            if not activation_20260707.get('ok'):
                raise RuntimeError(str(activation_20260707.get('message') or 'No loaded symbol reached the genuine minimum history.'))
            run_symbols_20260706 = list(activation_20260707.get('loaded_symbols') or [])
            from core.multi_symbol_run_groups_20260706 import mark_run_group
            active_group_20260706, run_symbols_20260706 = mark_run_group(st.session_state, selected_scope_20260701, run_symbols_20260706)
            try:
                from core.current_result_sync_20260708 import sync_settings_source_of_truth
                sync_settings_source_of_truth(st.session_state, configured_union_20260706 or ['EURUSD'], timeframe_for_load_20260707, reason='pre_queue_run_restore_selected_universe', clear_stale=False)
            except Exception as restore_selected_exc_20260708:
                st.session_state['pre_queue_current_selection_restore_error_20260708'] = f'{type(restore_selected_exc_20260708).__name__}: {restore_selected_exc_20260708}'
        except Exception as activation_exc_20260707:
            st.error(f'Calculation was not started: {type(activation_exc_20260707).__name__}: {activation_exc_20260707}. Reload a selector only if its market data is still below the genuine minimum or invalid.')
            return
        st.session_state['quota_safe_stagger_enabled_20260706'] = False
        st.session_state['super_quick_time_budget_enabled_20260706'] = False
        if selected_scope_20260701 == 'LUNCH_CORE':
            try:
                from core.super_quick_field3_20260722 import run_super_quick_field3
                fast_symbols = list(run_symbols_20260706)
                progress_slot = top_progress_slot_20260823

                def _super_quick_progress(snapshot):
                    try:
                        pct = float(snapshot.get('overall_percent') or 0.0)
                        stage = str(snapshot.get('current_stage') or 'Running')
                        progress_slot.progress(max(0.0, min(1.0, pct / 100.0)), text=f'{pct:.1f}% — {stage}')
                    except Exception:
                        pass
                fast_result = run_super_quick_field3(st.session_state, symbols=fast_symbols, timeframe=timeframe_for_load_20260707, progress_callback=_super_quick_progress)
                st.session_state['settings_run_status_20260617'] = fast_result
                st.success(f'Super Quick completed instantly from loaded cache for {len(fast_symbols)} symbol(s).' + (' Cached result reused.' if fast_result.get('reused_cached_calculation') else ''))
                _safe_rerun()
                return
            except Exception as super_fast_exc:
                error_text = f'{type(super_fast_exc).__name__}: {super_fast_exc}'
                st.session_state['super_quick_direct_fast_path_error_20260824'] = error_text
                st.session_state['settings_run_status_20260617'] = {'status': 'FAILED', 'ok': False, 'calculation_scope': 'SUPER_QUICK_FIELD3_THREE_TABLES', 'error': error_text, 'selected_symbols': list(fast_symbols), 'completed_symbols': 0, 'failed_symbols': len(fast_symbols)}
                for _lock_key in ('instant_run_engine_running_20260705', 'settings_one_click_running_20260624', 'multi_symbol_run_in_progress_20260701'):
                    st.session_state[_lock_key] = False
                st.error(f'Super Quick stopped safely before the slow calculation queue was started. {error_text}')
                return
    st.markdown('### Connections, API Keys and Provider Health')
    _render_mobile_api_key_center()
    _render_finnhub_connector_section()
    try:
        from ui.optional_provider_connectors_20260705 import render_optional_provider_connectors
        render_optional_provider_connectors(st.session_state)
    except Exception as optional_connector_exc:
        st.caption(f'Optional provider controls unavailable: {type(optional_connector_exc).__name__}')
    try:
        from ui.provider_health_panel_20260705 import render_provider_health_panel
        render_provider_health_panel(st.session_state)
    except Exception as provider_panel_exc:
        st.caption(f'Provider health panel unavailable: {type(provider_panel_exc).__name__}')
    if reset_col.button('🔄 Reset UI', key='settings_reset_ui_20260617', use_container_width=True):
        st.session_state['active_page'] = 'Settings'
        st.session_state['active_subpage'] = ''
        _safe_rerun()
    with st.expander('Open / Close — Trade Timer / Sound Alert', expanded=True):
        try:
            from ui.sidebar_fallback_panel import _render_timer
            _render_timer(key_prefix='settings_timer_20260619')
        except Exception as exc:
            st.warning(f'Trade timer skipped safely: {exc}')
    status = st.session_state.get('settings_run_status_20260617')
    if isinstance(status, dict):
        cols = st.columns(5)
        cols[0].metric('Last Run', 'READY' if status.get('ok') else 'PARTIAL')
        cols[1].metric('Generation', str(status.get('calculation_generation', '-')))
        cols[2].metric('Lunch Metric', 'READY' if (status.get('metric') or {}).get('ok') else 'CHECK')
        cols[3].metric('PowerBI', 'READY' if (status.get('powerbi') or {}).get('ok') else 'CHECK')
        cols[4].metric('Built At', str(status.get('built_at', '-')))
        if status.get('errors'):
            with st.expander('Open / Close — Last calculation status', expanded=False):
                st.dataframe(pd.DataFrame({'Status': list(status.get('errors') or [])}), use_container_width=True, hide_index=True)
        readiness = status.get('readiness') if isinstance(status.get('readiness'), dict) else st.session_state.get('system_wide_readiness_manifest_20260618')
        if isinstance(readiness, dict):
            component_rows = []
            for name, item in (readiness.get('components') or {}).items():
                item = item if isinstance(item, dict) else {}
                component_rows.append({'Component': name, 'Status': 'READY' if item.get('ready') else 'CHECK / ERROR', 'Rows': item.get('rows', 0), 'Detail': item.get('detail', '')})
            with st.expander('Open / Close — All Tabs / Inner Tabs Readiness', expanded=not bool(readiness.get('ready'))):
                st.dataframe(pd.DataFrame(component_rows), use_container_width=True, hide_index=True)
    try:
        from core.operational_sync_20260618 import collect_sync_health, errors_frame, clear_operational_errors
        health = pd.DataFrame(collect_sync_health(st.session_state))
        with st.expander('Open / Close — Synchronization Health', expanded=False):
            st.dataframe(health, use_container_width=True, hide_index=True)
        errors = errors_frame(st.session_state)
        has_errors = bool(len(errors)) if hasattr(errors, '__len__') else False
        with st.expander('Open / Close — Errors / Fix Fast', expanded=has_errors):
            if has_errors:
                st.dataframe(errors, use_container_width=True, hide_index=True)
                if st.button('Clear displayed errors', key='clear_operational_errors_20260618', use_container_width=True):
                    clear_operational_errors(st.session_state)
                    _safe_rerun()
            else:
                st.success('No captured calculation or renderer errors.')
    except Exception as exc:
        st.caption(f'Synchronization diagnostics unavailable: {exc}')
    try:
        from ui.decision_product_panel_20260617 import render_settings_product_status
        render_settings_product_status()
    except Exception as exc:
        st.caption(f'Decision diagnostics skipped safely: {exc}')

def render_settings_sidebar() -> None:
    """Render the complete Settings control surface in the native sidebar."""
    with st.sidebar:
        st.markdown('## ⚙️ Settings')
        st.caption('API, timeframe, candle history, symbol loading, keys, and Super Quick calculation')
        _render_settings()



def show(runtime_context: Any | None = None) -> None:
    """Registry-compatible Settings renderer; the live app exposes the same surface in the sidebar."""
    del runtime_context
    _render_settings()
