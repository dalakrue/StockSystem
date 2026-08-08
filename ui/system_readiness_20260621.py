"""Field 6: read-only future-strategy research and historical evidence.

This replaces the former generic A–F readiness checklist with bounded history
that is not duplicated in Lunch Fields 1–5. It never calculates a signal,
trains a model, or changes protected BUY/SELL/WAIT logic.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from services.canonical_snapshot_store import DB_PATH

VERSION = "future-strategy-research-history-20260621-v1"
MAX_VISIBLE_ROWS = 120

EVIDENCE_GROUPS: dict[str, tuple[str, ...]] = {
    "Model and feature history": (
        "ml_production_readiness_history",
        "model_x_knockoff_feature_history",
        "fforma_shadow_history",
        "expert_weight_history",
    ),
    "Forecast, calibration and comparison": (
        "conditional_predictive_ability_history",
        "research_spa_results",
        "covariate_shift_conformal_history",
        "flexible_loss_history",
    ),
    "Risk, adaptation and abstention": (
        "reject_option_history",
        "online_fdr_test_history",
        "expert_tracker_comparison",
        "bounded_quantile_monitoring_state",
        "sliding_monitoring_state",
    ),
    "Validation, invariants and promotion gates": (
        "monotonicity_validation_history",
        "delta_maintenance_history",
        "metamorphic_test_history",
        "calm_operation_classification",
        "evidence_gate_history",
        "research_paper_run",
    ),
}

# These are explanations of mechanisms already present in the package. They are
# not claims that the assumptions hold or that a trading-profit theorem exists.
THEORY_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "Method": "Conditional Predictive Ability",
        "Equation / property": "E[L_A,t - L_B,t | information_t]",
        "Hypothesis tested": "A challenger has lower conditional loss than the protected benchmark in a supported regime/session.",
        "Assumptions": "Forecasts precede outcomes; chronological settled samples; dependence-aware inference.",
        "EURUSD H1 relevance": "Detects when a model helps only in specific regimes rather than globally.",
        "Evidence table": "conditional_predictive_ability_history",
        "Production influence": "SHADOW: confirm, reduce confidence, or WAIT only",
        "Guarantee boundary": "No profitability or future-accuracy guarantee.",
    },
    {
        "Method": "Superior Predictive Ability / Model Confidence Set",
        "Equation / property": "max_j sqrt(n) * mean(loss_benchmark - loss_j) with dependent bootstrap",
        "Hypothesis tested": "Apparent best performance is not only data-snooping across many challengers.",
        "Assumptions": "Valid loss series, sufficient settled support, block bootstrap captures dependence.",
        "EURUSD H1 relevance": "Prevents promoting a lucky historical pattern/model.",
        "Evidence table": "research_spa_results",
        "Production influence": "Promotion gate only",
        "Guarantee boundary": "Controls a statistical comparison; it does not ensure live profit.",
    },
    {
        "Method": "FFORMA shadow weighting",
        "Equation / property": "forecast = sum_m w_m(x) forecast_m, with w_m >= 0 and sum_m w_m = 1",
        "Hypothesis tested": "Time-series features can identify which existing expert is more reliable for the current context.",
        "Assumptions": "Feature and loss definitions remain stable; validation is chronological.",
        "EURUSD H1 relevance": "Supports future adaptive weighting without creating a new direction engine.",
        "Evidence table": "fforma_shadow_history",
        "Production influence": "SHADOW disabled until reviewed promotion",
        "Guarantee boundary": "Empirical ensemble method; no theorem of market superiority.",
    },
    {
        "Method": "Fixed-share expert tracking",
        "Equation / property": "w_t+1 = (1-alpha) normalized(w_t exp(-eta loss_t)) + alpha/M",
        "Hypothesis tested": "The most useful existing expert can change after regime shifts.",
        "Assumptions": "Loss is settled sequentially; eta/share rates are bounded; no future outcome leakage.",
        "EURUSD H1 relevance": "Tracks changing model usefulness while limiting abrupt weight jumps.",
        "Evidence table": "expert_weight_history",
        "Production influence": "SHADOW evidence; cannot reverse direction",
        "Guarantee boundary": "Regret-style properties depend on bounded losses and tuning assumptions.",
    },
    {
        "Method": "Covariate-shift weighted conformal",
        "Equation / property": "Weighted residual quantile under bounded importance weights",
        "Hypothesis tested": "Intervals can remain useful when recent EURUSD H1 conditions differ from calibration history.",
        "Assumptions": "Exchangeability is replaced by a defensible weighting model; effective sample size is adequate.",
        "EURUSD H1 relevance": "Warns when coverage support is weak under a new volatility/regime mix.",
        "Evidence table": "covariate_shift_conformal_history",
        "Production influence": "Uncertainty/WAIT downgrade only",
        "Guarantee boundary": "Coverage claims are invalid when weighting assumptions or support fail.",
    },
    {
        "Method": "Model-X knockoff feature evidence",
        "Equation / property": "Swap-exchangeability with antisymmetric feature statistics and FDR thresholding",
        "Hypothesis tested": "A feature contributes beyond correlated alternatives in a supported historical window.",
        "Assumptions": "Knockoff construction approximates the feature distribution; sample support is sufficient.",
        "EURUSD H1 relevance": "Identifies unstable or redundant features before future ML promotion.",
        "Evidence table": "model_x_knockoff_feature_history",
        "Production influence": "Feature audit only",
        "Guarantee boundary": "FDR property depends on valid knockoffs; selection is not causal proof.",
    },
    {
        "Method": "Online false-discovery control",
        "Equation / property": "Sequential alpha allocation with bounded testing wealth",
        "Hypothesis tested": "Repeated research alerts are not accepted merely because many tests were tried.",
        "Assumptions": "Registered test order and dependence assumptions match the chosen procedure.",
        "EURUSD H1 relevance": "Reduces false confidence from repeated pattern/regime experiments.",
        "Evidence table": "online_fdr_test_history",
        "Production influence": "Research acceptance gate",
        "Guarantee boundary": "Controls false discoveries under stated assumptions, not trading losses.",
    },
    {
        "Method": "Reject option / selective prediction",
        "Equation / property": "Act only when estimated risk <= rejection cost threshold",
        "Hypothesis tested": "Abstaining on uncertain forecasts improves reliability among acted-on cases.",
        "Assumptions": "Risk estimates are calibrated on settled, leakage-safe history.",
        "EURUSD H1 relevance": "Allows BUY/SELL evidence to be downgraded to WAIT, never reversed.",
        "Evidence table": "reject_option_history",
        "Production influence": "WAIT downgrade only",
        "Guarantee boundary": "Higher selective accuracy can reduce coverage and does not imply profit.",
    },
    {
        "Method": "Monotonicity and metamorphic invariants",
        "Equation / property": "Defined input transformations must preserve or move outputs in a declared direction",
        "Hypothesis tested": "The system remains logically consistent under duplicate, reorder, scale, and append transformations.",
        "Assumptions": "Each relation is valid for the protected calculation contract.",
        "EURUSD H1 relevance": "Detects software defects that ordinary example tests may miss.",
        "Evidence table": "monotonicity_validation_history / metamorphic_test_history",
        "Production influence": "Publication block on critical failure",
        "Guarantee boundary": "Passing tested relations does not prove absence of all defects.",
    },
    {
        "Method": "Exact incremental maintenance",
        "Equation / property": "incremental_result(new rows) == full_recompute(same completed history)",
        "Hypothesis tested": "Future efficient updates preserve the same result as an exact recomputation.",
        "Assumptions": "Stable source prefix, deterministic logic/version, completed H1 identity.",
        "EURUSD H1 relevance": "Reduces CPU/RAM without silently changing historical outputs.",
        "Evidence table": "delta_maintenance_history",
        "Production influence": "Optimization gate only",
        "Guarantee boundary": "Equality applies only to tested versions and fixtures.",
    },
)

PREFERRED_COLUMNS = (
    "evaluated_at", "settled_at", "updated_at", "source_generation_id", "status",
    "evidence_status", "mode", "paper_number", "paper_title", "feature_name", "feature_group",
    "condition_name", "condition_value", "horizon", "model_a", "model_b", "loss_name",
    "settled_sample_count", "sample_count", "effective_sample_size", "mean_loss_difference",
    "effect_size", "test_statistic", "p_value", "spa_p_value", "best_challenger_id",
    "overall_readiness_score", "data_readiness_score", "model_readiness_score",
    "infrastructure_readiness_score", "monitoring_readiness_score", "expert_id",
    "previous_weight", "new_weight", "settled_loss", "raw_p_value", "allocated_alpha",
    "adjusted_result", "protected_decision", "shadow_decision", "accepted_risk_estimate",
    "contract_name", "relation_name", "operation_name", "gate_name", "gate_pass",
    "promotion_allowed", "production_influence_enabled", "all_gates_pass", "calculation_version",
)
TIME_COLUMNS = ("evaluated_at", "settled_at", "updated_at", "created_at", "timestamp")


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _read_only_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection | None:
    path = Path(db_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=2)
    except Exception:
        return None


def _existing_tables(db_path: Path | str = DB_PATH) -> set[str]:
    conn = _read_only_connection(db_path)
    if conn is None:
        return set()
    try:
        return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    allowed = {name for tables in EVIDENCE_GROUPS.values() for name in tables}
    if table not in allowed:
        return []
    return [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def load_research_history(
    table: str,
    *,
    db_path: Path | str = DB_PATH,
    limit: int = MAX_VISIBLE_ROWS,
    search: str = "",
) -> pd.DataFrame:
    """Load one bounded, projected table through a read-only SQLite handle."""
    allowed = {name for tables in EVIDENCE_GROUPS.values() for name in tables}
    if table not in allowed:
        return pd.DataFrame()
    conn = _read_only_connection(db_path)
    if conn is None:
        return pd.DataFrame()
    try:
        existing = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if table not in existing:
            return pd.DataFrame()
        columns = _table_columns(conn, table)
        selected = [name for name in PREFERRED_COLUMNS if name in columns][:24]
        if not selected:
            selected = [name for name in columns if name != "payload_json"][:16]
        if not selected:
            return pd.DataFrame()
        order_col = next((name for name in TIME_COLUMNS if name in columns), None)
        projection = ",".join(f'"{name}"' for name in selected)
        query = f'SELECT {projection} FROM "{table}"'
        if order_col:
            query += f' ORDER BY "{order_col}" DESC'
        query += " LIMIT ?"
        frame = pd.read_sql_query(query, conn, params=(int(max(1, min(limit, MAX_VISIBLE_ROWS))),))
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()
    term = str(search or "").strip().lower()
    if term and not frame.empty:
        mask = frame.astype(str).apply(lambda col: col.str.lower().str.contains(term, regex=False, na=False)).any(axis=1)
        frame = frame.loc[mask].reset_index(drop=True)
    return frame


def _table_row_counts(db_path: Path | str = DB_PATH) -> dict[str, int]:
    allowed = [name for tables in EVIDENCE_GROUPS.values() for name in tables]
    conn = _read_only_connection(db_path)
    if conn is None:
        return {name: 0 for name in allowed}
    try:
        existing = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        counts: dict[str, int] = {}
        for table in allowed:
            if table not in existing:
                counts[table] = 0
                continue
            try:
                counts[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except Exception:
                counts[table] = 0
        return counts
    finally:
        conn.close()


def build_future_strategy_snapshot(
    canonical: Mapping[str, Any],
    summary: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    db_path: Path | str = DB_PATH,
) -> dict[str, Any]:
    counts = _table_row_counts(db_path)
    available = sum(1 for value in counts.values() if value > 0)
    total_rows = int(sum(counts.values()))
    identity = _m(summary.get("identity"))
    generation = identity.get("calculation_generation") or canonical.get("calculation_generation")
    calculation_id = summary.get("calculation_id") or canonical.get("canonical_calculation_id") or canonical.get("run_id")
    stale = bool(
        state.get("dependent_calculations_stale_20260621")
        or state.get("canonical_display_stale_20260621")
        or canonical.get("stale")
        or _m(canonical.get("metadata")).get("stale")
    )
    if not canonical:
        status = "WAIT FOR CALCULATION"
    elif total_rows == 0:
        status = "INSUFFICIENT EVIDENCE"
    elif stale:
        status = "HISTORICAL GENERATION"
    else:
        status = "RESEARCH HISTORY AVAILABLE"
    return {
        "version": VERSION,
        "final_status": status,  # compatibility with the former master-control summary
        "calculation_id": calculation_id,
        "calculation_generation": generation,
        "latest_completed_h1": identity.get("latest_completed_candle_time") or canonical.get("latest_completed_candle_time"),
        "available_history_tables": available,
        "configured_history_tables": len(counts),
        "persisted_research_rows": total_rows,
        "table_row_counts": counts,
        "strategy_influence": "CONFIRM / LOWER CONFIDENCE / LOWER PRIORITY / WAIT ONLY",
        "direction_reversal_allowed": False,
        "production_influence_default": "SHADOW OR VALIDATION GATE",
        "limitations": (
            "Empty tables mean INSUFFICIENT EVIDENCE, not zero risk or zero effect.",
            "Statistical properties apply only when their assumptions and sample gates pass.",
            "This field does not calculate forecasts or trading decisions.",
        ),
    }


def build_readiness_snapshot(
    canonical: Mapping[str, Any],
    summary: Mapping[str, Any],
    state: Mapping[str, Any],
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible name for callers that read the former snapshot."""
    del plan
    return build_future_strategy_snapshot(canonical, summary, state)


def _canonical_research_rows(canonical: Mapping[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for key in (
        "research_validation_20260621", "ten_paper_research_20260621",
        "research_risk", "trust_validation", "history_evidence_summary",
    ):
        value = canonical.get(key)
        if isinstance(value, Mapping):
            rows.append({
                "Published canonical key": key,
                "Status": value.get("status") or value.get("validation_status") or value.get("production_status") or "PUBLISHED",
                "Sample support": value.get("sample_count") or value.get("settled_sample_count") or value.get("support_n") or "NOT REPORTED",
                "Promotion / influence": value.get("promotion_allowed") if "promotion_allowed" in value else value.get("production_influence_enabled", "SHADOW / PROTECTED"),
                "Limitation": value.get("limitation") or value.get("reason") or "Use only the published generation and its recorded assumptions.",
            })
    return pd.DataFrame(rows)


def render_system_readiness(*, state: MutableMapping[str, Any] | None = None) -> Mapping[str, Any]:
    """Render Field 6 while retaining the legacy callable name."""
    state = state if state is not None else st.session_state
    from core.canonical_runtime_20260617 import get_canonical
    from core.compact_canonical_20260619 import get_compact_summary

    canonical = get_canonical(state)
    summary = get_compact_summary(state)
    snapshot = build_future_strategy_snapshot(canonical, summary, state)
    state["system_readiness_snapshot_20260621"] = snapshot
    state["future_strategy_history_snapshot_20260621"] = snapshot

    st.markdown("### Future Strategy Research & Historical Evidence")
    st.caption(
        "Read-only evidence not duplicated in Lunch Fields 1–5: ML readiness, model comparison, "
        "calibration, adaptive weighting, abstention, validation invariants and promotion gates. "
        "Opening this field never trains, forecasts or changes direction."
    )
    cols = st.columns(4)
    cols[0].metric("Evidence status", snapshot["final_status"])
    cols[1].metric("Research history rows", snapshot["persisted_research_rows"])
    cols[2].metric("Tables with evidence", f"{snapshot['available_history_tables']}/{snapshot['configured_history_tables']}")
    cols[3].metric("Direction reversal", "PROHIBITED")

    published = _canonical_research_rows(canonical)
    if not published.empty:
        st.markdown("#### Current published research summary")
        st.dataframe(published, use_container_width=True, hide_index=True)

    choices = list(EVIDENCE_GROUPS) + ["Equation, theorem, concept and hypothesis registry"]
    group = st.selectbox("Future-strategy evidence group", choices, key="field6_research_group_20260621")

    if group == "Equation, theorem, concept and hypothesis registry":
        registry = pd.DataFrame(THEORY_REGISTRY)
        term = st.text_input("Search concepts, equations, assumptions or EURUSD H1 relevance", key="field6_theory_search_20260621")
        if term.strip():
            mask = registry.astype(str).apply(lambda col: col.str.lower().str.contains(term.strip().lower(), regex=False, na=False)).any(axis=1)
            registry = registry.loc[mask].reset_index(drop=True)
        st.dataframe(registry, use_container_width=True, hide_index=True, height=520)
        st.caption("A hypothesis is an assumption to test, not a guaranteed belief. No listed theorem guarantees profitable EURUSD H1 trading.")
    else:
        tables = EVIDENCE_GROUPS[group]
        counts = snapshot["table_row_counts"]
        table_labels = {name: f"{name} ({counts.get(name, 0)} rows)" for name in tables}
        selected = st.selectbox(
            "Historical evidence table",
            tables,
            format_func=lambda name: table_labels[name],
            key=f"field6_table_{''.join(ch for ch in group.lower() if ch.isalnum())[:40]}_20260621",
        )
        search = st.text_input("Search the selected bounded history", key=f"field6_search_{selected}_20260621")
        frame = load_research_history(selected, search=search)
        if frame.empty:
            st.info(
                "INSUFFICIENT EVIDENCE — this table has no settled rows for the packaged database/current generation, "
                "or no rows match the search. Run Calculation may publish future rows only when its evidence gates are met."
            )
        else:
            st.dataframe(frame, use_container_width=True, hide_index=True, height=500)
            st.download_button(
                "Export selected research history CSV",
                data=frame.to_csv(index=False).encode("utf-8"),
                file_name=f"{selected}_bounded.csv",
                mime="text/csv",
                key=f"field6_export_{selected}_20260621",
                use_container_width=True,
            )

    st.markdown("#### Strategy-use boundary")
    st.dataframe(pd.DataFrame([
        {"Rule": "Allowed effect", "Value": snapshot["strategy_influence"]},
        {"Rule": "Forbidden effect", "Value": "WAIT→BUY/SELL promotion; BUY↔SELL reversal"},
        {"Rule": "Data timing", "Value": "Completed and settled H1 evidence only"},
        {"Rule": "When unsupported", "Value": "Display INSUFFICIENT EVIDENCE"},
        {"Rule": "Statistical boundary", "Value": "Assumptions and sample gates must pass; no profit guarantee"},
    ]), use_container_width=True, hide_index=True)

    st.caption("Canonical Copy Short and Copy Full controls are intentionally available only at the top of Lunch.")
    return snapshot


__all__ = [
    "VERSION", "MAX_VISIBLE_ROWS", "EVIDENCE_GROUPS", "THEORY_REGISTRY",
    "load_research_history", "build_future_strategy_snapshot",
    "build_readiness_snapshot", "render_system_readiness",
]
