"""Publish one completed calculation generation to every existing workspace.

No formulas or prediction models live here.  The module validates and aliases the
objects already built by the Settings orchestrator so every tab/inner-tab reads
one immutable generation.  It also supplies precise readiness diagnostics instead
of showing a second generic "Run Calculation" gate after a successful run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

import pandas as pd

MANIFEST_KEY = "system_wide_readiness_manifest_20260618"
READY_KEY = "system_wide_calculation_ready_20260618"
METRIC_KEY = "lunch_metric_result_published_20260618"
DETAIL_TABLES_KEY = "regime_standard_detail_tables_published_20260618"
RESEARCH_KEY = "research_pack_20260612"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(value: Any) -> int:
    if isinstance(value, pd.DataFrame):
        return int(len(value))
    if isinstance(value, (list, tuple)):
        return int(len(value))
    return 0


def _ok_mapping(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and value.get("ok", True) is not False


def _identity(canonical: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": canonical.get("run_id"),
        "calculation_generation": canonical.get("calculation_generation"),
        "data_signature": canonical.get("data_signature"),
        "symbol": canonical.get("symbol", "EURUSD"),
        "timeframe": canonical.get("timeframe", "H1"),
        "source": canonical.get("source"),
        "latest_completed_candle_time": canonical.get("latest_completed_candle_time"),
    }


def _history_from_metric(metric_result: Any) -> pd.DataFrame:
    if not isinstance(metric_result, Mapping):
        return pd.DataFrame()
    history = metric_result.get("history")
    return history if isinstance(history, pd.DataFrame) else pd.DataFrame()


def _history_from_authority(authority: Any) -> pd.DataFrame:
    if not isinstance(authority, Mapping):
        return pd.DataFrame()
    for key in ("history", "history_table", "full_metric_history", "priority_table"):
        value = authority.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
    return pd.DataFrame()


def _regime_history(history: pd.DataFrame, priority_table: Any, canonical: Mapping[str, Any]) -> pd.DataFrame:
    source = history if isinstance(history, pd.DataFrame) and not history.empty else priority_table
    if not isinstance(source, pd.DataFrame) or source.empty:
        regime = canonical.get("regime") if isinstance(canonical.get("regime"), Mapping) else {}
        return pd.DataFrame([{
            "Time": canonical.get("latest_completed_candle_time"),
            "Regime": regime.get("major_regime", regime.get("current_regime", "UNKNOWN")),
            "Alpha": regime.get("alpha"),
            "Delta": regime.get("delta"),
            "Status": "CURRENT",
            "Run ID": canonical.get("run_id"),
            "Generation": canonical.get("calculation_generation"),
        }]) if canonical else pd.DataFrame()
    out = source.copy(deep=False)
    wanted = [c for c in out.columns if any(token in str(c).lower() for token in (
        "time", "date", "hour", "regime", "alpha", "delta", "direction",
        "decision", "reliability", "priority", "status", "row_id",
    ))]
    if wanted:
        out = out[wanted].copy(deep=False)
    time_col = next((c for c in ("Time", "time", "Datetime", "DateTime", "candle time") if c in out.columns), None)
    if time_col:
        parsed = pd.to_datetime(out[time_col], errors="coerce", utc=True)
        out = out.assign(_published_time=parsed).sort_values("_published_time", ascending=False, kind="stable").drop(columns=["_published_time"])
    return out.reset_index(drop=True)


def published_metric_result(state: Mapping[str, Any]) -> Mapping[str, Any]:
    value = state.get(METRIC_KEY)
    if isinstance(value, Mapping) and value.get("ok"):
        return value
    authority = state.get("full_metric_authority_20260618")
    if isinstance(authority, Mapping):
        result = authority.get("metric_result") or authority.get("source_result")
        if isinstance(result, Mapping) and result.get("ok"):
            return result
    return {}


def readiness_message(state: Mapping[str, Any], component: str) -> str:
    manifest = state.get(MANIFEST_KEY)
    manifest = manifest if isinstance(manifest, Mapping) else {}
    item = manifest.get(component)
    if isinstance(item, Mapping):
        if item.get("ready"):
            return f"Published generation {manifest.get('calculation_generation', '-')} is ready."
        detail = str(item.get("detail") or "No published rows were produced.")
        return f"Published generation {manifest.get('calculation_generation', '-')} could not prepare {component}: {detail}. Open Settings → Errors / Fix Fast."
    if state.get("settings_run_complete_20260617"):
        return f"The completed generation has no readiness record for {component}. Open Settings → Errors / Fix Fast."
    return "Use Settings → Run Calculation + Open Lunch once to publish the complete system generation."


def publish_system_wide_completion(
    state: MutableMapping[str, Any],
    *,
    canonical: Mapping[str, Any],
    adapter: Mapping[str, Any],
    priority_table: Any,
    metric_result: Any = None,
    regime_detail_tables: Any = None,
    nlp_result: Any = None,
    research_pack: Any = None,
    powerbi_status: Any = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Publish aliases and a per-component manifest for one canonical run."""
    identity = _identity(canonical)
    if not identity.get("run_id") or identity.get("calculation_generation") in (None, ""):
        raise ValueError("System-wide publication requires a complete canonical run identity")

    metric = metric_result if isinstance(metric_result, Mapping) else {}
    if metric.get("ok"):
        state[METRIC_KEY] = metric
        # Keep the exact same object under established cache aliases.
        state["lunch_metric_result_cache"] = metric
        state["full_metric_result_cache_20260618"] = metric

    if isinstance(regime_detail_tables, Mapping):
        state[DETAIL_TABLES_KEY] = regime_detail_tables
        state["regime_standard_detail_tables_20260617"] = regime_detail_tables

    if isinstance(nlp_result, Mapping) and nlp_result:
        state["nlp_market_intelligence_result"] = nlp_result
        state["nlp_result_published_20260618"] = nlp_result

    if isinstance(research_pack, Mapping) and research_pack:
        state[RESEARCH_KEY] = research_pack
        state["research_pack_published_20260618"] = research_pack

    if isinstance(priority_table, pd.DataFrame):
        state["canonical_priority_table_20260617"] = priority_table
        state["finder_readonly_priority_table_20260618"] = priority_table
        state["lunch_quick_decision_merged_table_20260617"] = priority_table

    history = _history_from_metric(metric)
    if history.empty:
        history = _history_from_authority(state.get("full_metric_authority_20260618"))
    if not history.empty:
        state["full_metric_history_df_20260618"] = history
    regime_history = _regime_history(history, priority_table, canonical)
    if not regime_history.empty:
        state["full_metric_regime_history_df"] = regime_history
        state["major_regime_history_df"] = regime_history

    # All old gates are marked complete only after canonical publication.
    state.update({
        "metric_run_calculate": True,
        "research_run_calculate": True,
        "other_run_calculate": True,
        "lunch_bi_visual_ready": bool((powerbi_status or {}).get("ok", state.get("lunch_bi_visual_ready", False))) if isinstance(powerbi_status, Mapping) else bool(state.get("lunch_bi_visual_ready", False)),
        "settings_auto_open_lunch_20260617": True,
        "settings_run_complete_20260617": True,
        "system_published_run_id_20260618": identity.get("run_id"),
        "system_published_generation_20260618": identity.get("calculation_generation"),
    })

    detail_counts = {
        str(k): _rows(v) for k, v in (regime_detail_tables.items() if isinstance(regime_detail_tables, Mapping) else [])
    }
    articles = nlp_result.get("articles") if isinstance(nlp_result, Mapping) else None
    research_analysis = research_pack.get("data_analysis") if isinstance(research_pack, Mapping) else None
    research_mining = research_pack.get("data_mining") if isinstance(research_pack, Mapping) else None
    components = {
        "Full Metric": {"ready": bool(metric.get("ok")), "rows": _rows(history), "detail": metric.get("message") if isinstance(metric, Mapping) else "Metric result missing"},
        "Lunch Priority": {"ready": isinstance(priority_table, pd.DataFrame) and not priority_table.empty, "rows": _rows(priority_table), "detail": "Canonical priority table is empty"},
        "Finder": {"ready": isinstance(priority_table, pd.DataFrame) and not priority_table.empty, "rows": _rows(priority_table), "detail": "Finder shares the canonical priority table"},
        "PowerBI": {"ready": bool((powerbi_status or {}).get("ok")) if isinstance(powerbi_status, Mapping) else bool(state.get("lunch_bi_visual_ready")), "rows": int((powerbi_status or {}).get("predicted_rows", 0)) if isinstance(powerbi_status, Mapping) else 0, "detail": (powerbi_status or {}).get("message") if isinstance(powerbi_status, Mapping) else "PowerBI cache missing"},
        "Regime Standards": {"ready": bool(detail_counts) and all(v > 0 for v in detail_counts.values()), "rows": sum(detail_counts.values()), "detail": f"Rows by window: {detail_counts}"},
        "Regime History": {"ready": not regime_history.empty, "rows": _rows(regime_history), "detail": "Restored below Full Metric History"},
        "NLP 10-Day News": {"ready": isinstance(articles, pd.DataFrame) and len(articles) > 0, "rows": _rows(articles), "detail": "Real recent-news rows available; fewer than 10 is shown honestly when sources return fewer"},
        "Research Data Analysis": {"ready": _ok_mapping(research_analysis), "rows": _rows((research_analysis or {}).get("diagnostic_table")) if isinstance(research_analysis, Mapping) else 0, "detail": (research_analysis or {}).get("message") if isinstance(research_analysis, Mapping) else "Analysis pack missing"},
        "Research Data Mining": {"ready": _ok_mapping(research_mining), "rows": _rows((research_mining or {}).get("knn_priority")) if isinstance(research_mining, Mapping) else 0, "detail": (research_mining or {}).get("message") if isinstance(research_mining, Mapping) else "Mining pack missing"},
        "AI Grounding": {"ready": bool(adapter.get("ai_grounding") or state.get("ai_synced_snapshot_20260618")), "rows": 0, "detail": "Uses the same canonical run"},
    }
    # A completed canonical generation must not be blocked by optional display
    # packs (PowerBI/research/NLP) returning fewer rows or a transient warning.
    # Full Metric + shared priority + regime history are the publication gates;
    # other components stay visible in diagnostics without forcing every tab back
    # to the generic Run Calculation message.
    essential = ("Full Metric", "Lunch Priority", "Finder", "Regime History")
    ready = all(bool(components[name]["ready"]) for name in essential)
    manifest = {
        **identity,
        "ready": ready,
        "status": "READY" if ready else "PARTIAL_WITH_VISIBLE_ERRORS",
        "published_at": _now(),
        "components": components,
        "errors": list(errors or []),
    }
    # Direct component lookup keeps renderer code tiny.
    manifest.update(components)
    state[MANIFEST_KEY] = manifest
    state[READY_KEY] = ready
    return manifest


__all__ = [
    "MANIFEST_KEY", "READY_KEY", "METRIC_KEY", "DETAIL_TABLES_KEY",
    "published_metric_result", "readiness_message", "publish_system_wide_completion",
]
