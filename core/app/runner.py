import streamlit as st
import warnings
from core.streamlit_compat_20260615 import install_streamlit_compat

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    def st_autorefresh(*args, **kwargs):
        return None

from core.common import init_state
from core.styles import apply_global_styles
from core.ui_relationship import init_ui_relationship_state, sync_shared_connection_signature
from core.system_contract import init_system_contract, maybe_persist_runtime_snapshot, update_data_quality_from_session
from core.app.lifecycle import _safe_run_page
from core.app.routes import load_tab
from core.app.refresh import run_deferred_refresh
from core.code_quality import run_light_maintenance
from core.pro_quality_upgrade import repair_session_contract
from core.global_upgrade import apply_extra_css, apply_dedup_metric_css
from core.pro_terminal_uiux import apply_pro_terminal_css, apply_pro_terminal_runtime_helpers, render_pro_command_center_bar, render_pro_popup_layer
from core.v6_final_ui_logic_patch import install_runtime as install_v6_runtime
from core.full_system_upgrade import apply_v21_uiux, render_popup
from core.streamlit_safe_dataframe import install_safe_dataframe_patch
from core.websocket_payload_guard_20260629 import install_websocket_payload_guard
from core.ui.app_polish import apply_next_level_uiux, render_real_app_header
from core.galileo_theme_20260612 import apply_galileo_theme
from core.state_manager import init_future_safety_guard
from ui.app_shell import inject_mobile_css, render_main_menu_drawer, render_top_status_bar, render_ui_health_check
from ui.home_master_control_bar_20260615 import render_home_master_control_bar
from ui.sidebar_hard_lock import init_sidebar_policy, inject_sidebar_policy_css
from ui.liquid_glass_theme_20260615 import apply_liquid_glass_theme
from ui.mobile_table_alignment_20260722 import inject_mobile_table_alignment

from core.adx_shared_sync_20260615 import ensure_shared_calculation_result, install_phone_safety_defaults
from core.tab_state_stability_20260615 import stabilize_tab_state
from core.navigation_state_20260627 import initialize_navigation, commit_requested_page
from core.canonical_runtime_20260617 import begin_rerun, build_runtime_context
from ui.mobile_low_heat_20260617 import apply_mobile_low_heat_css, should_enable_full_autorefresh
from core.mobile_lite_mode_20260628 import initialize_mobile_lite_mode, extreme_mobile_css


def run_app():
    warnings.filterwarnings(
        "ignore",
        message=r"y_pred contains classes not in y_true",
        category=UserWarning,
        module=r"sklearn\.metrics\._classification",
    )
    try:
        install_streamlit_compat()
    except Exception:
        pass

    try:
        install_safe_dataframe_patch()
    except Exception:
        pass

    try:
        install_websocket_payload_guard()
    except Exception:
        pass

    try:
        from core.structured_result_display_20260617 import install_structured_result_display
        install_structured_result_display()
    except Exception:
        pass

    try:
        st.set_page_config(page_title="ADX Quant Pro — Field 3", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")
    except Exception:
        pass

    # The dashboard is intentionally login-free.  It opens directly into the
    # single Field 3 workspace and keeps configuration in the native sidebar.
    st.session_state.setdefault("new7_auth_logged_in", True)
    st.session_state.setdefault("new7_auth_guest", True)
    st.session_state.setdefault("new7_auth_email", "Guest")

    try:
        init_state()
        try:
            from core.complete_repair_20260705 import (
                ensure_canonical_multi_symbol_state,
                migrate_complete_repair_schema,
            )
            if not st.session_state.get("complete_repair_schema_checked_20260705"):
                migration = migrate_complete_repair_schema(create_backup=False)
                from core.data.deployment_migrations_20260705 import migrate_deployment_schema, DEFAULT_DB_PATH
                deployment_migration = migrate_deployment_schema(DEFAULT_DB_PATH)
                st.session_state["complete_repair_migration_report_20260705"] = migration
                st.session_state["deployment_migration_report_20260705"] = deployment_migration
                st.session_state["complete_repair_schema_checked_20260705"] = True
            try:
                from core.connectors.credential_vault import restore_into_state
                st.session_state["credential_vault_restore_20260705"] = restore_into_state(st.session_state)
            except Exception:
                st.session_state.setdefault("credential_vault_restore_20260705", {})
            try:
                from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
                from core.runtime_selection_20260705 import load_runtime_preferences, synchronize_runtime_selection
                synchronize_runtime_selection(st.session_state, persisted=load_runtime_preferences(DEFAULT_DB_PATH))
            except Exception:
                pass
            ensure_canonical_multi_symbol_state(st.session_state)
        except Exception as repair_exc:
            try:
                from core.complete_repair_20260705 import log_internal_error
                st.session_state["complete_repair_startup_incident_20260705"] = log_internal_error("app.complete_repair_startup", repair_exc)
            except Exception:
                st.session_state["complete_repair_startup_incident_20260705"] = "STARTUP-REPAIR"
        # Restore the last completed, secret-free canonical generation before
        # startup guards inspect the state. A browser refresh therefore keeps
        # the latest published Lunch/Dinner data without recalculation.
        try:
            from core.runtime_state_cache_20260628 import restore_runtime_state
            restore_runtime_state(st.session_state)
        except Exception as restore_exc:
            st.session_state["runtime_warm_cache_restore_error_20260628"] = f"{type(restore_exc).__name__}: {restore_exc}"
        begin_rerun(st.session_state)
        init_future_safety_guard()
        init_sidebar_policy()
        init_system_contract()
        init_ui_relationship_state()
        try:
            from core.v9_architecture_guard_20260702 import install_global_symbol_state, publish_v9_canonical_state
            install_global_symbol_state(st.session_state)
            publish_v9_canonical_state(st.session_state, force=False, reason="startup")
        except Exception as v9_guard_exc:
            st.session_state["v9_architecture_guard_startup_error_20260702"] = f"{type(v9_guard_exc).__name__}: {v9_guard_exc}"
        try:
            install_phone_safety_defaults()
            initialize_navigation(st.session_state)
            try:
                from core.navigation_transaction_20260622 import consume_pending_navigation
                consume_pending_navigation(st.session_state)
            except Exception:
                pass
            commit_requested_page(st.session_state)
            stabilize_tab_state()
        except Exception:
            pass
    except Exception as exc:
        try:
            from core.complete_repair_20260705 import log_internal_error
            incident = log_internal_error("app.state_initialization", exc)
        except Exception:
            incident = "STATE-INIT"
        st.error(f"App state initialization failed safely. Support reference: {incident}.")
        return

    # Resolve Mobile Lite once per session before optional startup work and style
    # imports. This changes presentation/orchestration only and never calculation.
    try:
        initialize_mobile_lite_mode(st, st.session_state)
    except Exception as mobile_exc:
        st.session_state["mobile_lite_initialization_error_20260628"] = f"{type(mobile_exc).__name__}: {mobile_exc}"

    # Connect deployment-secret providers once immediately after Guest/account
    # login. This performs no heavy calculation and never changes the page.
    try:
        from core.secure_api_startup_20260619 import run_guarded_startup
        run_guarded_startup(st.session_state)
    except Exception as exc:
        st.session_state["secure_api_startup_error_20260706"] = f"{type(exc).__name__}: {exc}"

    # Deterministic startup remains read-only; Settings owns every heavy run.
    try:
        from core.startup_lunch_orchestrator_20260704 import run_startup
        run_startup(st.session_state)
    except Exception as exc:
        st.session_state["lunch_startup_error_20260704"] = f"{type(exc).__name__}: {exc}"

    try:
        phone_mode = bool(st.session_state.get("phone_mode", False))
        st.session_state["logic_first_mobile_20260618"] = bool(phone_mode)
        apply_global_styles(phone_mode)
        apply_extra_css()
        apply_dedup_metric_css()
        # Phone mode intentionally omits stacked decorative themes, animated
        # backgrounds and terminal overlays. Calculation/render logic is kept.
        if not phone_mode:
            apply_pro_terminal_css()
            apply_pro_terminal_runtime_helpers()
            apply_v21_uiux()
            apply_next_level_uiux()
            apply_galileo_theme()
            apply_liquid_glass_theme()
            try:
                from ui.safe_tab_switch_20260615 import inject_motion_background_css
                inject_motion_background_css()
            except Exception:
                pass
        inject_mobile_css()
        inject_mobile_table_alignment(st, phone_mode=phone_mode)
        st.markdown(extreme_mobile_css(bool(st.session_state.get("extreme_mobile_lite_mode_20260628"))), unsafe_allow_html=True)
        inject_sidebar_policy_css()
        apply_mobile_low_heat_css(st, phone_mode)
    except Exception as exc:
        try:
            from core.complete_repair_20260705 import log_internal_error
            incident = log_internal_error("app.styles", exc)
        except Exception:
            incident = "STYLE"
        st.warning(f"Some visual styles were skipped; calculations remain available. Support reference: {incident}.")

    try:
        if st.session_state.get("ws_enabled", False):
            try:
                from core.websocket_feed import consume_websocket_into_session
                consume_websocket_into_session()
            except Exception:
                pass
        nav_age = __import__("time").time() - float(st.session_state.get("ui_navigation_click_ts", 0.0) or 0.0)
        fast_nav = bool(st.session_state.get("fast_tab_switch_active", False)) or nav_age < 2.5
        if not fast_nav:
            run_deferred_refresh()
            run_light_maintenance()
            repair_session_contract()
        else:
            st.session_state["deferred_auto_refresh_reason"] = "Skipped refresh/maintenance for fast tab switch."
    except Exception as exc:
        try:
            from core.complete_repair_20260705 import log_internal_error
            incident = log_internal_error("app.deferred_refresh", exc)
        except Exception:
            incident = "REFRESH"
        st.warning(f"Automatic refresh was skipped; the saved snapshot is still usable. Support reference: {incident}.")

    try:
        update_data_quality_from_session(persist=False)
        sync_shared_connection_signature()
        maybe_persist_runtime_snapshot("app_cycle")
    except Exception:
        pass

    try:
        inject_sidebar_policy_css()
        # Native sidebar is the single Settings control surface.
        st.session_state["use_native_sidebar_fallback_20260619"] = True
        initialize_navigation(st.session_state)
        tab = commit_requested_page(st.session_state)
        stabilize_tab_state()
        tab = str(st.session_state.get("active_page") or "Settings")
    except Exception as exc:
        try:
            from core.complete_repair_20260705 import log_internal_error
            incident = log_internal_error("app.navigation", exc)
        except Exception:
            incident = "NAVIGATION"
        st.warning(f"Navigation used a safe fallback. Support reference: {incident}.")
        try:
            from ui.navigation_registry import normalize_active_tab
            tab = normalize_active_tab(st.session_state.get("tab_choice", st.session_state.get("active_page", "Settings")))
        except Exception:
            tab = st.session_state.get("tab_choice", "Settings") or "Settings"
        st.session_state["active_page"] = tab
        st.session_state["tab_choice"] = tab

    try:
        # Field 3 is the only main page.  The former main-page drawer and
        # duplicate status/command rails are intentionally not rendered.
        st.session_state["active_page"] = "Field 3"
        st.session_state["tab_choice"] = "Field 3"
        st.session_state["active_subpage"] = ""
        tab = "Field 3"
        inject_sidebar_policy_css()
    except Exception:
        pass

    # Resolve navigation once, synchronize once, then pass a lightweight runtime
    # context to the selected renderer. Hidden pages and inner tabs remain idle.
    try:
        try:
            from core.navigation_transaction_20260622 import consume_pending_navigation
            consume_pending_navigation(st.session_state)
        except Exception:
            pass
        tab = "Field 3"
        st.session_state["active_page"] = tab
        st.session_state["tab_choice"] = tab
        stabilize_tab_state()
        tab = "Field 3"
        subpage = str(st.session_state.get("active_subpage", "") or "")
        ensure_shared_calculation_result(force=False)
        try:
            from core.v9_architecture_guard_20260702 import publish_v9_canonical_state
            publish_v9_canonical_state(st.session_state, force=False, reason="pre_render")
        except Exception as v9_guard_exc:
            st.session_state["v9_architecture_guard_prerender_error_20260702"] = f"{type(v9_guard_exc).__name__}: {v9_guard_exc}"
        try:
            from core.operational_sync_20260618 import ensure_generation_consistency
            generation_sync = ensure_generation_consistency(st.session_state)
        except Exception as exc:
            generation_sync = {"ok": False, "status": "CHECK", "error": str(exc)}
        runtime_context = build_runtime_context(
            st.session_state, active_page=tab, active_subpage=subpage,
            phone_mode=bool(st.session_state.get("phone_mode", False)),
        )
        runtime_context["generation_sync"] = generation_sync
    except Exception as exc:
        try:
            from core.operational_sync_20260618 import record_operational_error
            record_operational_error(st.session_state, "Runtime synchronization", exc, stage="runtime")
        except Exception:
            pass
        try:
            from core.complete_repair_20260705 import log_internal_error
            incident = log_internal_error("app.runtime_sync", exc)
        except Exception:
            incident = "RUNTIME-SYNC"
        runtime_context = {"active_page": tab, "active_subpage": "", "canonical_status": "DATA NOT READY", "incident_id": incident}

    try:
        if should_enable_full_autorefresh(st.session_state, tab, str(runtime_context.get("active_subpage", ""))):
            st_autorefresh(interval=600000, key="ten_min_refresh")
        else:
            st.session_state["ten_min_refresh_disabled_reason_20260617"] = "Phone low-heat mode or non-live/closed page"
    except Exception:
        pass

    # Render every configuration control in the sidebar while keeping the
    # analytical Field 3 result as the sole main-page surface.
    try:
        from tabs.antd_page_router_20260615 import render_settings_sidebar
        render_settings_sidebar()
    except Exception as sidebar_exc:
        st.sidebar.error(f"Settings sidebar could not render: {type(sidebar_exc).__name__}: {sidebar_exc}")

    show = load_tab("Field 3")
    _safe_run_page(tab, show, runtime_context=runtime_context)
    try:
        from core.navigation_transaction_20260622 import confirm_lunch_navigation
        confirm_lunch_navigation(st.session_state, tab)
    except Exception:
        pass
    try:
        # Final CSS wins over any old tab-level sidebar styles.
        inject_sidebar_policy_css()
    except Exception:
        pass
    st.session_state["fast_tab_switch_active"] = False
