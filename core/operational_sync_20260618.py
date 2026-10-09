"""Lightweight synchronization and visible error diagnostics.

No formulas live here.  It mirrors one atomically-published canonical generation
into read-only page aliases, validates that every workspace points at the same
run, and retains a small redacted error ledger for fast repair.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Mapping, MutableMapping

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

ERROR_KEY = "operational_error_ledger_20260618"
SYNC_KEY = "operational_sync_status_20260618"
MAX_ERRORS = 24

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_ -]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b[A-Za-z0-9_-]{28,}\b"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_message(value: Any, limit: int = 500) -> str:
    text = str(value or "Unknown error").replace("\x00", " ").strip()
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: match.group(0).split(":", 1)[0].split("=", 1)[0] + ": [REDACTED]", text)
    return text[: max(80, int(limit))]


def record_operational_error(state: MutableMapping[str, Any], component: str, error: Any, *, stage: str = "render") -> dict[str, Any]:
    row = {
        "time_utc": _now(),
        "component": str(component or "Unknown component")[:100],
        "stage": str(stage or "runtime")[:60],
        "message": redact_message(error),
    }
    rows = state.get(ERROR_KEY)
    rows = list(rows) if isinstance(rows, list) else []
    # Avoid filling the phone session with the same rerun error.
    signature = (row["component"], row["stage"], row["message"])
    if not rows or (rows[-1].get("component"), rows[-1].get("stage"), rows[-1].get("message")) != signature:
        rows.append(row)
    state[ERROR_KEY] = rows[-MAX_ERRORS:]
    return row


def clear_operational_errors(state: MutableMapping[str, Any]) -> None:
    state[ERROR_KEY] = []


def error_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = state.get(ERROR_KEY)
    return list(rows)[-MAX_ERRORS:] if isinstance(rows, list) else []


def errors_frame(state: Mapping[str, Any]):
    rows = list(reversed(error_rows(state)))
    if pd is None:
        return rows
    return pd.DataFrame(rows, columns=["time_utc", "component", "stage", "message"])


def _identity(canonical: Mapping[str, Any]) -> dict[str, Any]:
    market = canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}
    return {
        "run_id": canonical.get("run_id"),
        "calculation_generation": canonical.get("calculation_generation"),
        "data_signature": canonical.get("data_signature"),
        "symbol": canonical.get("symbol"),
        "timeframe": canonical.get("timeframe"),
        "source": canonical.get("source"),
        "latest_completed_candle_time": canonical.get("latest_completed_candle_time") or market.get("latest_completed_candle_time"),
    }


def _stamped_component(identity: Mapping[str, Any], payload: Any) -> dict[str, Any]:
    """Return a shallow read-only view stamped with the canonical identity.

    Nested adapters such as NLP and Full Metric History are often ordinary
    payload dictionaries and do not carry ``run_id``/generation themselves.
    The old health panel therefore reported false MISMATCH/MISSING states even
    though the parent canonical generation was valid.  Stamping the read-only
    alias fixes the architecture contract without changing any calculation.
    """
    if isinstance(payload, Mapping):
        view = dict(payload)
    else:
        view = {"payload": payload} if payload is not None else {}
    # Canonical identity always wins over a stale nested identity.
    view.update(dict(identity))
    view["sync_payload_available"] = bool(payload)
    return view


def synchronize_published_generation(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any],
    adapter: Mapping[str, Any],
    priority_table: Any = None,
) -> dict[str, Any]:
    """Mirror references to one canonical generation without recalculation/copies."""
    identity = _identity(canonical)
    if not identity.get("run_id") or not identity.get("calculation_generation"):
        raise ValueError("Cannot synchronize an incomplete canonical generation")

    final = canonical.get("final_decision") if isinstance(canonical.get("final_decision"), Mapping) else {}
    shared_current = adapter.get("current") if isinstance(adapter.get("current"), Mapping) else {}
    page_snapshot = {
        **identity,
        "status": "CURRENT",
        "decision": final.get("final_decision", "WAIT"),
        "direction": final.get("directional_market_view", canonical.get("full_metric_direction", "WAIT")),
        "less_risky_decision": final.get("less_risky_decision", "WAIT"),
        "selected_horizon": final.get("selected_horizon"),
        "current": shared_current,
    }

    # These are references to the same immutable published objects, not new calculations.
    full_metric_payload = adapter.get("full_metric_snapshot")
    if not full_metric_payload:
        full_metric_payload = canonical.get("full_metric_snapshot", {})
    aliases = {
        "lunch_synced_snapshot_20260618": page_snapshot,
        "dinner_synced_snapshot_20260618": page_snapshot,
        "finder_synced_snapshot_20260618": page_snapshot,
        "research_synced_snapshot_20260618": page_snapshot,
        "ai_synced_snapshot_20260618": page_snapshot,
        "morning_synced_snapshot_20260619": page_snapshot,
        "data_visualization_synced_snapshot_20260619": page_snapshot,
        "priority_synced_snapshot_20260619": page_snapshot,
        "train_data_synced_snapshot_20260619": page_snapshot,
        "backtest_synced_snapshot_20260619": page_snapshot,
        "profile_synced_snapshot_20260619": page_snapshot,
        "engine_synced_snapshot_20260619": page_snapshot,
        "pre_original_synced_snapshot_20260619": page_snapshot,
        "shared_adapter_synced_snapshot_20260707": _stamped_component(identity, adapter),
        "risk_plan_synced_20260619": _stamped_component(identity, canonical.get("risk_plan", {})),
        "nlp_synced_adapter_20260618": _stamped_component(identity, adapter.get("nlp", {})),
        "data_mining_synced_adapter_20260618": _stamped_component(identity, adapter.get("data_mining", {})),
        "powerbi_synced_adapter_20260618": _stamped_component(identity, adapter.get("powerbi", {})),
        "regime_synced_adapter_20260618": _stamped_component(identity, adapter.get("regime", {})),
        "reliability_synced_adapter_20260618": _stamped_component(identity, adapter.get("reliability", {})),
        "full_metric_synced_snapshot_20260618": _stamped_component(identity, full_metric_payload),
    }
    for key, value in aliases.items():
        state[key] = value
    if priority_table is not None:
        state["finder_readonly_priority_table_20260618"] = priority_table

    # Publish the compact summary and AI fact pack in the same synchronization
    # transaction. This prevents Lunch Field 5 from showing "Run Calculation"
    # after a successful Settings/Menu run when optional page caches were cleared.
    try:
        from core.compact_canonical_20260619 import publish_compact_runtime
        summary, fact_pack = publish_compact_runtime(state, canonical, adapter)
        aliases["compact_canonical_summary_20260619"] = {"calculation_id": summary.get("calculation_id")}
        aliases["ai_fact_pack_20260619"] = {"calculation_id": fact_pack.get("calculation_id"), "size_bytes": fact_pack.get("size_bytes")}
    except Exception as exc:
        state["compact_runtime_publish_error_20260621"] = redact_message(exc)

    status = {
        **identity,
        "ok": True,
        "status": "SYNCED",
        "published_at": _now(),
        "aliases": sorted(aliases),
        "priority_rows": int(len(priority_table)) if hasattr(priority_table, "__len__") else 0,
    }
    state[SYNC_KEY] = status
    return status


def collect_sync_health(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    canonical = state.get("canonical_decision_result_20260617")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    expected = _identity(canonical)
    if not expected.get("run_id"):
        return [{"Component": "Canonical calculation", "Status": "NOT READY", "Detail": "Run Calculation in Settings"}]

    checks = [
        ("Canonical calculation", canonical),
        ("Shared adapter", state.get("shared_adapter_synced_snapshot_20260707") or state.get("adx_shared_calc_result_20260615")),
        ("Lunch", state.get("lunch_synced_snapshot_20260618")),
        ("Dinner", state.get("dinner_synced_snapshot_20260618")),
        ("Finder", state.get("finder_synced_snapshot_20260618")),
        ("Research / AI", state.get("research_synced_snapshot_20260618")),
        ("NLP", state.get("nlp_synced_adapter_20260618")),
        ("Regime history", state.get("full_metric_synced_snapshot_20260618")),
    ]
    rows: list[dict[str, Any]] = []
    for label, component in checks:
        if not isinstance(component, Mapping) or not component:
            rows.append({"Component": label, "Status": "MISSING", "Detail": "No current published view"})
            continue
        got_run = component.get("run_id")
        got_generation = component.get("calculation_generation")
        if str(got_run) == str(expected.get("run_id")) and str(got_generation) == str(expected.get("calculation_generation")):
            availability = component.get("sync_payload_available")
            suffix = " • payload empty" if availability is False else ""
            rows.append({"Component": label, "Status": "SYNCED", "Detail": f"Generation {expected.get('calculation_generation')}{suffix}"})
        else:
            rows.append({"Component": label, "Status": "MISMATCH", "Detail": "Run/generation differs from canonical"})

    # Include every one-click completion component so the user can identify the
    # exact failed inner section instead of seeing a generic second-run prompt.
    manifest = state.get("system_wide_readiness_manifest_20260618")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    for label, item in (manifest.get("components") or {}).items():
        if not isinstance(item, Mapping):
            continue
        rows.append({
            "Component": f"Completion / {label}",
            "Status": "READY" if item.get("ready") else "CHECK / ERROR",
            "Detail": f"Rows {item.get('rows', 0)} • {item.get('detail') or ''}".strip(),
        })
    return rows


def ensure_generation_consistency(state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Reload stale read-only aliases from the last completed canonical snapshot."""
    canonical = state.get("canonical_decision_result_20260617")
    adapter = state.get("adx_shared_calc_result_20260615")
    if not isinstance(canonical, Mapping) or not isinstance(adapter, Mapping):
        return {"ok": False, "status": "NOT_READY"}
    expected = _identity(canonical)
    keys = (
        "shared_adapter_synced_snapshot_20260707",
        "lunch_synced_snapshot_20260618", "dinner_synced_snapshot_20260618",
        "finder_synced_snapshot_20260618", "research_synced_snapshot_20260618",
        "ai_synced_snapshot_20260618", "morning_synced_snapshot_20260619",
        "data_visualization_synced_snapshot_20260619", "train_data_synced_snapshot_20260619",
        "nlp_synced_adapter_20260618", "full_metric_synced_snapshot_20260618",
    )
    stale = False
    for key in keys:
        item = state.get(key)
        if not isinstance(item, Mapping) or str(item.get("run_id")) != str(expected.get("run_id")) or str(item.get("calculation_generation")) != str(expected.get("calculation_generation")):
            stale = True
            break
    if stale:
        table = state.get("canonical_priority_table_20260617")
        return synchronize_published_generation(state, canonical, adapter, table)
    return {**expected, "ok": True, "status": "CURRENT"}


__all__ = [
    "SYNC_KEY", "ERROR_KEY", "record_operational_error", "clear_operational_errors",
    "error_rows", "errors_frame", "synchronize_published_generation", "ensure_generation_consistency", "collect_sync_health",
]
