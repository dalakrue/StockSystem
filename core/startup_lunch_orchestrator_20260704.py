"""Deterministic Lunch startup and provider readiness orchestration.

Provider priority is Finnhub first, Twelve Data fallback, then MT5/validated
local storage. Startup is read-only: it restores connector and snapshot state but
never starts a heavy calculation. Only Settings may publish a new run.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from hashlib import sha256
import json
import time
from typing import Any

VERSION = "lunch-startup-orchestrator-20260705-v2"
STATE_KEY = "lunch_startup_state_20260704"
REPORT_KEY = "lunch_startup_report_20260704"
IDENTITY_KEY = "lunch_startup_identity_20260704"
LAST_COMPLETED_KEY = "lunch_startup_last_completed_identity_20260704"
VALID_STATES = (
    "NOT_CHECKED", "CHECKING_CONNECTORS", "PLAN_B_REQUIRED", "AUTO_RUN_QUEUED",
    "AUTO_RUN_RUNNING", "AUTO_RUN_PUBLISHED", "AUTO_RUN_FAILED",
)


def build_auto_run_identity(*, user_mode: str, completed_h1: str, symbols: Sequence[str],
                            timeframe: str, connector_profile_signature: str,
                            calculation_version: str = VERSION) -> str:
    material = {
        "user_mode": str(user_mode), "completed_h1": str(completed_h1),
        "symbols": [str(s).upper() for s in symbols], "timeframe": str(timeframe).upper(),
        "connector_profile_signature": sha256(str(connector_profile_signature).encode()).hexdigest(),
        "calculation_version": str(calculation_version),
    }
    return sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _cached_health(state: Mapping[str, Any], ttl_seconds: int = 900) -> dict[str, Any] | None:
    cached = state.get("connector_health_snapshot_20260704")
    if not isinstance(cached, Mapping):
        return None
    checked = float(cached.get("checked_at", 0.0) or 0.0)
    return dict(cached) if time.time() - checked <= ttl_seconds else None


def connector_health(state: MutableMapping[str, Any], ttl_seconds: int = 900) -> dict[str, Any]:
    cached = _cached_health(state, ttl_seconds)
    if cached is not None:
        cached["reused"] = True
        return cached

    profile = state.get("market_connector_saved_profile_20260702") if isinstance(
        state.get("market_connector_saved_profile_20260702"), Mapping
    ) else {}
    source = str(state.get("source") or "").upper()
    mode = str(profile.get("mode") or state.get("connector_mode") or "").lower()

    mt5_ok = bool(
        state.get("mt5_connected")
        or state.get("doo_bridge_connected")
        or (state.get("connected") and ("MT5" in source or mode == "mt5"))
    )
    twelve_configured = bool(state.get("twelve_api_key"))
    finnhub_configured = bool(state.get("finnhub_api_key"))
    try:
        from core.secure_api_startup_20260619 import secure_secret_status

        secure = secure_secret_status(state)
        twelve_configured = bool(twelve_configured or secure.get("second_api_configured"))
        finnhub_configured = bool(finnhub_configured or secure.get("finnhub_configured"))
    except Exception:
        pass

    twelve_ok = bool(
        twelve_configured
        and (
            state.get("twelve_data_connected")
            or state.get("twelve_connected")
            or state.get("twelve_last_success")
            or state.get("second_api_last_success")
            or mode == "twelve"
        )
    )
    finnhub_ok = bool(
        finnhub_configured
        and (state.get("finnhub_connected") or state.get("finnhub_last_success"))
    )
    result: dict[str, Any] = {
        "twelve_data": {
            "configured": twelve_configured,
            "healthy": twelve_ok,
            "last_success": state.get("twelve_last_success") or state.get("second_api_last_success"),
        },
        "finnhub": {
            "configured": finnhub_configured,
            "healthy": finnhub_ok,
            "last_success": state.get("finnhub_last_success"),
        },
        "mt5": {
            "configured": bool(mode == "mt5" or state.get("doo_bridge_url") or mt5_ok),
            "healthy": mt5_ok,
            "optional": True,
        },
        "checked_at": time.time(), "ttl_seconds": ttl_seconds, "reused": False,
    }
    # Keep provider roles stable even when the active provider is temporarily
    # unhealthy. Health and actual-use fields are reported separately so a
    # Twelve Data fallback response can never promote Twelve to configured active.
    provider_order = ("finnhub", "twelve_data", "mt5")
    actual_healthy = next((name for name in provider_order if result[name]["healthy"]), None)
    actual_fallback = next((name for name in provider_order if name != actual_healthy and result[name]["healthy"]), None)
    try:
        from core.data.market_data_orchestrator import provider_priority_for_state
        configured_plan = provider_priority_for_state(state)
    except Exception:
        configured_plan = ("FINNHUB", "TWELVE_DATA", "MT5", "LOCAL_VALID_CACHE")
    configured_active = str(configured_plan[0] if configured_plan else "FINNHUB").upper()
    configured_fallback = str(configured_plan[1] if len(configured_plan) > 1 else "TWELVE_DATA").upper()
    result["active_provider"] = configured_active.lower()
    result["fallback_provider"] = configured_fallback.lower()
    result["actual_healthy_provider"] = actual_healthy
    result["actual_healthy_fallback"] = actual_fallback
    result["any_healthy"] = actual_healthy is not None
    # Retained for old callers/tests; optional MT5 does not block Finnhub/Twelve.
    result["all_healthy"] = all(result[name]["configured"] and result[name]["healthy"] for name in provider_order)
    state["active_market_provider_20260705"] = configured_active
    state["fallback_market_provider_20260705"] = configured_fallback
    state["actual_healthy_market_provider_20260708"] = str(actual_healthy or "LOCAL_DATABASE").upper()
    state["connector_health_snapshot_20260704"] = result
    return result


def _load_persisted_snapshot() -> tuple[bool, dict[str, Any], str | None]:
    try:
        from core.field10_daily_snapshot_contract_20260702 import load_current_daily_snapshot

        persisted = load_current_daily_snapshot()
        metadata = persisted.get("metadata") if isinstance(persisted, Mapping) else {}
        rows = persisted.get("current") if isinstance(persisted, Mapping) else None
        return bool(metadata) and rows is not None and not rows.empty, dict(metadata or {}), None
    except Exception as exc:
        from core.complete_repair_20260705 import log_internal_error

        return False, {}, log_internal_error("startup.load_persisted_snapshot", exc)


def _guest_auto_run(state: MutableMapping[str, Any], health: Mapping[str, Any]) -> dict[str, Any] | None:
    """Run the historical Guest super-quick path once per completed candle.

    This path is entered only with an authenticated guest and fully verified
    connector health.  Ordinary account startup remains read-only.
    """
    if not (state.get("new7_auth_logged_in") and state.get("new7_auth_guest") and health.get("all_healthy")):
        return None
    canonical = state.get("canonical_decision_result_20260617") if isinstance(
        state.get("canonical_decision_result_20260617"), Mapping
    ) else {}
    completed = str(
        canonical.get("completed_broker_candle")
        or canonical.get("latest_completed_candle")
        or state.get("latest_completed_candle")
        or ""
    )
    if not completed:
        return None
    profile = state.get("market_connector_saved_profile_20260702") if isinstance(
        state.get("market_connector_saved_profile_20260702"), Mapping
    ) else {}
    try:
        from core.top15_fx_qualification_20260704 import qualify_mt5_top15

        qualification = qualify_mt5_top15()
    except Exception as exc:
        from core.complete_repair_20260705 import log_internal_error

        return {"ok": False, "status": "AUTO_RUN_FAILED", "incident_id": log_internal_error("startup.qualify", exc)}
    selected = list(qualification.get("selected") or []) if isinstance(qualification, Mapping) else []
    if not qualification.get("ok") or not selected:
        return None
    identity = build_auto_run_identity(
        user_mode="guest",
        completed_h1=completed,
        symbols=selected,
        timeframe=str(profile.get("timeframe") or state.get("timeframe") or "H4"),
        connector_profile_signature=str(profile.get("signature") or "saved-profile"),
    )
    state[IDENTITY_KEY] = identity
    if state.get(LAST_COMPLETED_KEY) == identity:
        return {
            "ok": True, "status": "AUTO_RUN_PUBLISHED", "state": "AUTO_RUN_PUBLISHED",
            "idempotent_reuse": True, "heavy_run_started": False,
            "selected_symbols": selected,
        }
    state[STATE_KEY] = "AUTO_RUN_RUNNING"
    try:
        from core.super_quick_service_20260704 import run_super_quick

        result = run_super_quick(state, selected)
    except Exception as exc:
        from core.complete_repair_20260705 import log_internal_error

        return {"ok": False, "status": "AUTO_RUN_FAILED", "incident_id": log_internal_error("startup.super_quick", exc)}
    if not isinstance(result, Mapping) or not result.get("ok"):
        return {"ok": False, "status": "AUTO_RUN_FAILED", "result_status": (result or {}).get("status") if isinstance(result, Mapping) else "UNKNOWN"}
    state[LAST_COMPLETED_KEY] = identity
    return {
        "ok": True, "status": "AUTO_RUN_PUBLISHED", "state": "AUTO_RUN_PUBLISHED",
        "idempotent_reuse": False, "heavy_run_started": True,
        "parent_run_id": result.get("parent_run_id") or (result.get("manifest") or {}).get("parent_run_id"),
        "selected_symbols": selected,
    }


def run_startup(state: MutableMapping[str, Any]) -> dict[str, Any]:
    state.setdefault(STATE_KEY, "NOT_CHECKED")
    if state.get("new7_auth_logged_in") and not state.get("first_settings_route_committed_20260706"):
        state["active_page"] = "Settings"
        state["tab_choice"] = "Settings"
        state["requested_page"] = "Settings"
        state["first_settings_route_committed_20260706"] = True

    state[STATE_KEY] = "CHECKING_CONNECTORS"
    health = connector_health(state)

    # Heavy startup calculation is intentionally disabled. The only authority
    # for a new canonical generation is Settings → Run Calculation + Open Lunch.
    auto = None
    if auto is not None and auto.get("status") == "AUTO_RUN_PUBLISHED":
        report = {
            **auto,
            "connector_health": health,
            "active_provider": health.get("active_provider"),
            "fallback_provider": health.get("fallback_provider") or "local_database",
            "message": "The completed Guest run was published once for this candle.",
            "version": VERSION,
        }
        state[STATE_KEY] = "AUTO_RUN_PUBLISHED"
        state[REPORT_KEY] = report
        return report
    if auto is not None and auto.get("status") == "AUTO_RUN_FAILED":
        # Keep going: an existing complete snapshot remains a valid read-only fallback.
        state["startup_auto_run_failure_20260705"] = dict(auto)

    has_snapshot, metadata, snapshot_incident = _load_persisted_snapshot()
    provider_ready = bool(health.get("any_healthy") or health.get("all_healthy"))
    runtime_identity_available = bool(
        state.get("canonical_decision_result_20260617")
        or state.get("canonical_result_20260617")
        or state.get("multi_symbol_manifest_20260701")
        or state.get("runtime_state_cache_restored_20260628")
    )
    if has_snapshot and (provider_ready or runtime_identity_available):
        report = {
            "ok": True,
            "status": "AUTO_RUN_PUBLISHED",
            "state": "AUTO_RUN_PUBLISHED",
            "idempotent_reuse": True,
            "heavy_run_started": False,
            "daily_snapshot_id": metadata.get("daily_snapshot_id"),
            "broker_day": metadata.get("broker_day"),
            "active_provider": health.get("active_provider") or "local_database",
            "fallback_provider": health.get("fallback_provider") or "canonical_snapshot",
            "connector_health": health,
            "message": "The latest complete Lunch publication was restored read-only.",
            "version": VERSION,
        }
        state[STATE_KEY] = "AUTO_RUN_PUBLISHED"
    else:
        blockers = [
            name for name in ("twelve_data", "finnhub")
            if not bool((health.get(name) or {}).get("healthy"))
        ]
        if not provider_ready:
            blockers.append("local_database_or_canonical_snapshot")
        report = {
            "ok": False,
            "status": "PLAN_B_REQUIRED",
            "state": "PLAN_B_REQUIRED",
            "blocking_connectors": blockers or ["complete_canonical_snapshot"],
            "heavy_run_started": False,
            "recommended_mode": "Super Quick Calculation + Open Lunch",
            "message": (
                "No complete Lunch publication is ready. Run one Settings button: "
                "Super Quick Calculation + Open Lunch, Quick Calculation + Open Lunch, "
                "or Full Calculation + Open Lunch. Super Quick is recommended for the fastest rebuild."
            ),
            "connector_health": health,
            "version": VERSION,
        }
        if snapshot_incident:
            report["incident_id"] = snapshot_incident
        state[STATE_KEY] = "PLAN_B_REQUIRED"
    state[REPORT_KEY] = report
    return report


def render_status(state: Mapping[str, Any]) -> None:
    import streamlit as st

    report = state.get(REPORT_KEY) if isinstance(state.get(REPORT_KEY), Mapping) else {
        "state": state.get(STATE_KEY, "NOT_CHECKED")
    }
    status = str(report.get("state") or report.get("status") or "NOT_CHECKED")
    with st.container(border=True):
        st.markdown("#### Startup Status")
        if status == "AUTO_RUN_PUBLISHED":
            st.success("A complete Lunch publication is ready. Opening fields does not recalculate it.")
            st.caption(
                f"Active provider: {report.get('active_provider') or 'local database'} · "
                f"Fallback: {report.get('fallback_provider') or 'canonical snapshot'}"
            )
        elif status == "AUTO_RUN_RUNNING":
            st.info("The one-time startup calculation is in progress.")
        elif status == "PLAN_B_REQUIRED":
            st.warning(str(report.get("message") or "A Settings calculation is required."))
        elif status == "AUTO_RUN_FAILED":
            st.warning("Startup could not publish a new run. The latest complete snapshot remains protected.")
        else:
            st.caption(status)
        blockers = report.get("blocking_connectors") or []
        if blockers:
            st.caption("Unavailable sources: " + ", ".join(map(str, blockers)))
        if report.get("incident_id"):
            st.caption(f"Support reference: {report['incident_id']}")


__all__ = [
    "VERSION", "STATE_KEY", "REPORT_KEY", "build_auto_run_identity",
    "connector_health", "run_startup", "render_status",
]
