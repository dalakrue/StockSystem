"""Display-only renderer for the published Similar-Day Intelligence payload."""
from __future__ import annotations

import html
from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st


_CARD_ORDER = (
    "Current pattern family",
    "Best historical match date",
    "Best Similarity Index",
    "Top-five directional agreement",
    "Weighted historical result",
    "Weighted median H+1 movement",
    "Weighted median H+3 movement",
    "Weighted median H+6 movement",
    "Historical expected range",
    "Historical MFE",
    "Historical MAE",
    "Effective sample size",
    "Current-regime compatibility",
    "Data quality",
    "Similar-day reliability",
    "Conflict with canonical current decision",
)

_PIP_FIELDS = {
    "Weighted median H+1 movement", "Weighted median H+3 movement", "Weighted median H+6 movement",
    "Historical expected range", "Historical MFE", "Historical MAE",
}
_PERCENT_FIELDS = {"Current-regime compatibility", "Data quality"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _published(state: MutableMapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(state)
    except Exception:
        canonical = state.get("canonical_decision_result_20260617") or state.get("canonical_result_20260617") or {}
    if isinstance(canonical, Mapping):
        value = canonical.get("similar_day_intelligence")
        if isinstance(value, Mapping):
            return value
    fallback = state.get("similar_day_intelligence_20260619")
    return fallback if isinstance(fallback, Mapping) else {}


def _format_value(label: str, value: Any) -> str:
    if value in (None, "", "Unavailable"):
        return "Unavailable"
    if label in _PIP_FIELDS:
        try:
            return f"{float(value):+.2f} pips"
        except Exception:
            return str(value)
    if label in _PERCENT_FIELDS:
        try:
            return f"{float(value):.1f}/100"
        except Exception:
            return str(value)
    if label == "Best Similarity Index":
        try:
            return f"{float(value):.2f}/100"
        except Exception:
            return str(value)
    return str(value)


def _render_cards(summary: Mapping[str, Any]) -> None:
    cards = []
    for label in _CARD_ORDER:
        value = _format_value(label, summary.get(label))
        warning = label == "Conflict with canonical current decision" and str(value).lower().startswith("conflict")
        cards.append(
            f'<div class="sd-card{" sd-warning" if warning else ""}">'
            f'<div class="sd-label">{html.escape(label)}</div>'
            f'<div class="sd-value">{html.escape(value)}</div></div>'
        )
    st.markdown(
        """
        <style>
        .sd-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin:.35rem 0 1rem}
        .sd-card{border:1px solid rgba(128,128,128,.25);border-radius:16px;padding:.8rem .85rem;
          background:linear-gradient(135deg,rgba(255,255,255,.10),rgba(255,255,255,.025));
          box-shadow:0 8px 24px rgba(0,0,0,.08);min-height:86px;overflow-wrap:anywhere}
        .sd-warning{border-color:rgba(255,140,80,.65)}
        .sd-label{font-size:.78rem;opacity:.72;line-height:1.25;margin-bottom:.35rem}
        .sd-value{font-size:1.02rem;font-weight:700;line-height:1.3}
        @media(max-width:1000px){.sd-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:760px){.sd-grid{grid-template-columns:1fr}.sd-card{min-height:auto;padding:.72rem .78rem}}
        </style>
        <div class="sd-grid">""" + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


def _frame(records: Any) -> pd.DataFrame:
    if not isinstance(records, list):
        return pd.DataFrame()
    rows = [dict(row) for row in records if isinstance(row, Mapping)]
    return pd.DataFrame.from_records(rows)


def _baseline_frame(payload: Mapping[str, Any]) -> pd.DataFrame:
    baselines = _mapping(payload.get("baselines"))
    labels = (
        ("Previous-day continuation", "previous_day_continuation_pips"),
        ("Same-weekday median", "same_weekday_median_pips"),
        ("Current-regime historical median", "current_regime_median_pips"),
        ("Rolling mean forecast", "rolling_mean_pips"),
        ("Exponentially weighted forecast", "exponentially_weighted_pips"),
        ("Existing canonical Power BI projection", "existing_powerbi_h3_pips"),
    )
    return pd.DataFrame([
        {"Baseline": label, "H+3 Forecast (pips)": baselines.get(key) if baselines.get(key) is not None else "Unavailable"}
        for label, key in labels
    ])


def _validation_frame(payload: Mapping[str, Any]) -> pd.DataFrame:
    validation = _mapping(payload.get("walk_forward_validation"))
    metrics = _mapping(validation.get("metrics"))
    rows = []
    for method, values in metrics.items():
        item = _mapping(values)
        rows.append({
            "Method": str(method).replace("_", " ").title(),
            "Status": item.get("status", "Unavailable"),
            "Samples": item.get("samples", 0),
            "MAE (pips)": item.get("mae_pips", "Unavailable"),
            "Direction Accuracy": f"{item.get('direction_accuracy_pct')}%" if item.get("direction_accuracy_pct") is not None else "Unavailable",
        })
    return pd.DataFrame(rows)



_REQUESTED_TABLES = (
    ("current_hour_core_metrics_history", "Table 4A — Current-Hour Core Metrics History"),
    ("decision_outcome_history", "Table 4B — Decision and Outcome History"),
    ("regime_compatibility_history", "Table 4C — Regime Compatibility History"),
    ("pattern_recognition_history", "Table 4D — Pattern Recognition History"),
    ("powerbi_forecast_calibration_history", "Table 4E — Power BI Forecast Calibration History"),
)


def render_requested_25day_tables(payload: Mapping[str, Any]) -> None:
    """Render the five fixed-schema tables published by the canonical run."""
    st.markdown("#### Five 25-Day History Tables")
    st.caption("All outcome columns are attached only after similarity ranking. Future H+1/H+3/H+6 values never enter matching features.")
    for key, title in _REQUESTED_TABLES:
        st.markdown(f"##### {title}")
        frame = _frame(payload.get(key))
        if frame.empty:
            if key == "powerbi_forecast_calibration_history":
                st.info("No settled Power BI forecast-history rows were available in this generation. The table will populate after forecasts settle.")
            else:
                st.info(f"{title} is unavailable in this completed generation.")
            continue
        st.dataframe(frame.head(25), use_container_width=True, hide_index=True, height=min(460, 90 + len(frame.head(25)) * 28))
        st.caption(f"Rows shown: {len(frame.head(25))}. Newest/strongest available historical rows are shown first.")

def _history_view(history: pd.DataFrame, view: str) -> pd.DataFrame:
    """Column presets over one canonical history frame; never duplicate rows."""
    if not isinstance(history, pd.DataFrame) or history.empty or view == "Complete view":
        return history
    aliases = {
        "Compact Decision view": ("date", "time", "rank", "similarity", "decision", "direction", "priority", "result", "reason"),
        "Forecast view": ("date", "time", "forecast", "predicted", "actual", "h+1", "h+2", "h+3", "h+6", "error", "lower", "upper", "power bi", "xgboost", "lstm", "transformer", "prophet"),
        "Regime view": ("date", "time", "regime", "transition", "alpha", "delta", "compatibility", "drift"),
        "Reliability view": ("date", "time", "reliability", "confidence", "quality", "conflict", "uncertainty", "calibration", "coverage", "warning"),
    }
    tokens = aliases.get(view, ())
    selected = [str(column) for column in history.columns if any(token in str(column).lower() for token in tokens)]
    # Always retain rank/date identity when present.
    for column in history.columns:
        if str(column).lower() in {"top five", "rank", "historical date", "date", "time", "timestamp"} and str(column) not in selected:
            selected.insert(0, str(column))
    return history[selected].copy() if selected else history


def _descending_history(history: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(history, pd.DataFrame) or history.empty:
        return history
    candidates = [column for column in history.columns if any(token in str(column).lower() for token in ("date", "time", "timestamp"))]
    for column in candidates:
        parsed = pd.to_datetime(history[column], errors="coerce", utc=True)
        if parsed.notna().any():
            return history.assign(__sort_time=parsed).sort_values("__sort_time", ascending=False, kind="stable").drop(columns="__sort_time").reset_index(drop=True)
    return history.reset_index(drop=True)


def render_similar_day_intelligence(*, state: MutableMapping[str, Any] | None = None) -> None:
    """Render steps 1–5 in the protected Field-4 order; never calculate."""
    state = state if state is not None else st.session_state
    payload = _published(state)

    # 1. Similar-Day Intelligence summary
    st.markdown("#### 1. Similar-Day Intelligence Summary")
    if not payload or not payload.get("ok"):
        reason = payload.get("message") if isinstance(payload, Mapping) else None
        st.info(
            "Similar-Day Intelligence is unavailable for this generation. "
            + (str(reason) if reason else "Run Calculation + Open Lunch after sufficient completed EURUSD H1 history is available.")
        )
        st.caption("Existing All Current Data remains available below. No calculation was attempted while opening this field.")
        return
    summary = _mapping(payload.get("summary"))
    st.write(
        f"**{summary.get('Current pattern family', 'Unclassified')}** · "
        f"best match **{summary.get('Best historical match date', 'Unavailable')}** · "
        f"Similarity Index **{_format_value('Best Similarity Index', summary.get('Best Similarity Index'))}** · "
        f"{summary.get('Similar-day reliability', 'Low Reliability')}"
    )
    st.caption(
        f"Completed UTC H1 prefix: {payload.get('elapsed_hour_count', 0)} candles through {payload.get('latest_completed_h1_timestamp', '-')}. "
        f"Engine {payload.get('engine_version', '-')}; feature set {payload.get('feature_version', '-')}"
    )

    # 2. Summary cards
    st.markdown("#### 2. Summary Cards")
    _render_cards(summary)

    # 3. Top-five similar results
    st.markdown("#### 3. Top-Five Similar Results")
    top = _frame(payload.get("top_five"))
    if top.empty:
        st.info("No sufficiently complete historical match reached the top-five table.")
    else:
        preferred = [
            "Rank", "Historical Date", "Similarity Index", "Price Shape Score", "Regime Match",
            "H+1 Direction", "H+1 Pips", "H+3 Direction", "H+3 Pips", "H+6 Direction", "H+6 Pips",
            "Historical Less-Risky Decision", "Data Quality",
        ]
        visible = [column for column in preferred if column in top.columns]
        st.dataframe(top[visible] if visible else top, use_container_width=True, hide_index=True, height=245)

    # 4. Complete descending 25-day history table with column presets.
    st.markdown("#### 4. Complete Descending 25-Day History Table")
    history = _descending_history(_frame(payload.get("history_25")))
    if history.empty:
        st.info("The complete 25-day attempted-candidate table is unavailable.")
    else:
        if "Top Five" not in history.columns:
            rank = history.get("Rank", pd.Series(index=history.index, dtype=float))
            history.insert(0, "Top Five", rank.map(lambda value: "★" if pd.notna(value) and int(value) <= 5 else ""))
        view = st.selectbox(
            "History column view",
            ("Compact Decision view", "Forecast view", "Regime view", "Reliability view", "Complete view"),
            index=0,
            key="similar_day_history_view_20260621",
            help="All presets read the same canonical 25-day history. Complete view exposes every preserved field.",
        )
        display = _history_view(history, view)
        st.dataframe(display, use_container_width=True, hide_index=True, height=520)
        st.caption(
            f"Rows shown: {len(history)}. {view} displays {len(display.columns)} of {len(history.columns)} preserved fields. "
            "Complete view exposes every field; no physical history table is duplicated."
        )

    # 5. Explanation and reliability warning
    st.markdown("#### 5. Similarity Explanation and Reliability Warning")
    st.info(str(payload.get("explanation") or "Similarity Index is supporting historical evidence, not probability."))
    conflict = str(payload.get("conflict_warning") or "")
    if conflict:
        st.warning(conflict)
    reliability = str(payload.get("reliability") or summary.get("Similar-day reliability") or "Low Reliability")
    if reliability == "Low Reliability":
        st.warning("Low Reliability: do not use Similar-Day Intelligence as an entry signal. The canonical Full Metric, priority, reliability and Power BI result remain authoritative.")
    else:
        st.caption(f"Reliability gate: {reliability}. Similar-Day evidence remains supporting evidence only and cannot override the canonical decision.")

    baselines = _baseline_frame(payload)
    if not baselines.empty:
        st.markdown("##### Baseline Comparison")
        st.dataframe(baselines, use_container_width=True, hide_index=True, height=250)
    validation = _validation_frame(payload)
    if not validation.empty:
        with st.expander("Open / Close — Cached walk-forward validation", expanded=False):
            st.dataframe(validation, use_container_width=True, hide_index=True, height=260)
            st.caption(str(_mapping(payload.get("walk_forward_validation")).get("claim") or "No superiority claim is made without sufficient settled samples."))
    with st.expander("Open / Close — Five preserved 25-day history tables", expanded=False):
        render_requested_25day_tables(payload)


__all__ = ["render_similar_day_intelligence", "render_requested_25day_tables"]
