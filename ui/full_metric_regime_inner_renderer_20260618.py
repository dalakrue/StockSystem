"""Read-only Medium/Higher regime display for the canonical Full Metric run.

The calculation orchestrator creates all regime standards exactly once.  This
module only reads the published generation, renders current major-regime cards,
and sends the Medium (about five days) and Higher (about 25 days) tables to the
browser.  Raw current-hour/every-hour duplicates remain available internally and
in existing exports but are deliberately not rendered here.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import pandas as pd
import streamlit as st

from ui.table_ordering_20260618 import chronological_view


_FRAGMENT = getattr(st, "fragment", lambda fn: fn)
_TIME_NAMES = ("Time", "time", "Datetime", "DateTime", "Date", "Timestamp", "Hour", "candle time")
_PREFERRED_MOBILE_COLUMNS = (
    "Time", "Date", "Hour", "Major Regime", "Current Regime", "Regime Direction",
    "Alpha", "Delta", "Transition Risk %", "Regime Reliability", "Reliability /10",
    "Regime Score /10", "Less Risky Bias", "KNN Priority", "KNN Score /10",
    "Greedy Priority", "Greedy Score /10", "Priority", "Decision", "Direction",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(mapping: Mapping[str, Any], *names: str, default: Any = "-") -> Any:
    for name in names:
        value = mapping.get(name)
        if value not in (None, ""):
            return value
    return default


def _canonical(state: MutableMapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        return value if isinstance(value, Mapping) else {}
    except Exception:
        value = state.get("canonical_result_20260617") or state.get("canonical_result")
        return value if isinstance(value, Mapping) else {}


def _latest_full_metric_row(result: Mapping[str, Any] | None) -> Mapping[str, Any]:
    history = _mapping(result or {}).get("history")
    if not isinstance(history, pd.DataFrame) or history.empty:
        return {}
    view = chronological_view(history, row_limit=1)
    return view.iloc[0].to_dict() if not view.empty else {}


def _alpha_delta_interpretation(alpha: Any, delta: Any) -> str:
    try:
        a, d = float(alpha), float(delta)
    except Exception:
        return "Published synchronized values"
    if abs(a) < 1e-9 and abs(d) >= 1e-9:
        return "Transition / reversal risk"
    if abs(a) < 1e-9:
        return "Range / compression"
    if a > 0 and d > 0:
        return "Bullish advantage strengthening"
    if a > 0 and d < 0:
        return "Bullish advantage weakening"
    if a < 0 and d < 0:
        return "Bearish advantage strengthening"
    if a < 0 and d > 0:
        return "Bearish advantage weakening"
    return "Directional advantage stable"


def build_existing_regime_summary(
    result: Mapping[str, Any] | None = None,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Build cards from already-published values; never invoke a regime builder."""
    state = state if state is not None else st.session_state
    canonical = _canonical(state)
    regime = _mapping(canonical.get("regime"))
    context = _mapping(state.get("regime_context_20260614"))
    metrics = _mapping(context.get("metrics"))
    latest = _latest_full_metric_row(result)

    current = _first(
        metrics, "Current Regime",
        default=_first(regime, "current_regime", "major_regime", default=_first(latest, "Current Regime", "Regime", "Major Regime")),
    )
    major = _first(regime, "major_regime", default=_first(latest, "Major Regime", "Current Major Regime", default=current))
    alpha = _first(regime, "alpha", default=_first(latest, "Alpha", "Regime Alpha"))
    delta = _first(regime, "delta", default=_first(latest, "Delta", "Regime Delta"))
    reliability = _first(metrics, "Regime Reliable Score", "Regime Reliability", default=_first(regime, "reliability", "regime_reliability"))
    transition = _first(metrics, "Transition Risk %", default=_first(regime, "transition_probability", "transition_risk"))
    rows = [
        {"Regime Field": "Current Major Regime", "Value": major},
        {"Regime Field": "Current Regime", "Value": current},
        {"Regime Field": "Regime Reliability", "Value": reliability},
        {"Regime Field": "Alpha", "Value": alpha},
        {"Regime Field": "Delta", "Value": delta},
        {"Regime Field": "Transition Risk", "Value": transition},
        {"Regime Field": "Expected Remaining Hours", "Value": _first(metrics, "Estimated Remaining Hours", default=_first(regime, "expected_remaining_hours"))},
        {"Regime Field": "Interpretation", "Value": _alpha_delta_interpretation(alpha, delta)},
        {"Regime Field": "Run ID", "Value": canonical.get("run_id", "-")},
        {"Regime Field": "Latest Completed H1", "Value": canonical.get("latest_completed_candle_time", "-")},
    ]
    return pd.DataFrame(rows)


def _published_detail_tables(state: MutableMapping[str, Any]) -> Mapping[str, Any]:
    for key in (
        "regime_standard_detail_tables_published_20260618",
        "regime_standard_detail_tables_20260617",
    ):
        value = state.get(key)
        if isinstance(value, Mapping):
            return value
    canonical = _canonical(state)
    regime = _mapping(canonical.get("regime"))
    for key in ("standard_detail_tables", "detail_tables", "regime_standard_detail_tables"):
        value = regime.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def collect_existing_regime_tables(
    result: Mapping[str, Any] | None = None,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> list[tuple[str, pd.DataFrame]]:
    """Return only published Medium/Higher standards, preserving raw histories internally."""
    del result
    state = state if state is not None else st.session_state
    details = _published_detail_tables(state)
    output: list[tuple[str, pd.DataFrame]] = []
    for key, title in (("medium", "Medium Standard Regime — About 5 Days"), ("higher", "Higher Standard Regime — About 25 Days")):
        frame = details.get(key)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            output.append((title, frame))
    return output


def _mobile_projection(frame: pd.DataFrame) -> pd.DataFrame:
    """Project display columns only; complete columns remain in stored/export data."""
    chosen = [name for name in _PREFERRED_MOBILE_COLUMNS if name in frame.columns]
    if not chosen:
        return frame
    # Keep a readable bounded view while retaining key regime/KNN/Greedy fields.
    return frame.loc[:, list(dict.fromkeys(chosen))[:18]]


@_FRAGMENT
def _render_standard_table(title: str, frame: pd.DataFrame, *, key_prefix: str) -> None:
    show_all_columns = st.toggle(
        f"Show all stored columns for {title.split(' — ')[0]}",
        value=False,
        key=f"{key_prefix}_all_columns_20260619",
    )
    ordered = chronological_view(frame, row_limit=None)
    display = ordered if show_all_columns else _mobile_projection(ordered)
    phone = bool(st.session_state.get("phone_mode", False))
    default_rows = 60 if phone else 160
    row_choices = [30, 60, 120, 240]
    default_index = row_choices.index(default_rows) if default_rows in row_choices else 1
    row_limit = st.selectbox(
        f"Visible rows — {title.split(' — ')[0]}",
        row_choices,
        index=default_index,
        key=f"{key_prefix}_row_limit_20260619",
    )
    display = display.head(int(row_limit)).reset_index(drop=True)
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        height=min(520, max(260, 44 + min(len(display), 17) * 28)),
    )
    if st.toggle(f"Prepare complete {title.split(' — ')[0]} CSV", value=False, key=f"{key_prefix}_export_toggle_20260619"):
        st.download_button(
            f"Export Complete {title.split(' — ')[0]} CSV",
            data=ordered.to_csv(index=False).encode("utf-8"),
            file_name=f"eurusd_h1_{key_prefix}_regime_complete.csv",
            mime="text/csv",
            key=f"{key_prefix}_export_20260619",
            use_container_width=True,
        )


def render_existing_regime_inner_section(
    result: Mapping[str, Any] | None = None,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    """Render major cards, then Medium and Higher standards in requested order."""
    state = state if state is not None else st.session_state
    st.markdown("#### Current Major Regime")
    summary = build_existing_regime_summary(result, state=state)
    values = dict(zip(summary["Regime Field"], summary["Value"])) if not summary.empty else {}
    cards = st.columns(3)
    cards[0].metric("Major Regime", str(values.get("Current Major Regime", "-")))
    cards[1].metric("Regime Reliability", str(values.get("Regime Reliability", "-")))
    cards[2].metric("Transition Risk", str(values.get("Transition Risk", "-")))
    cards2 = st.columns(3)
    cards2[0].metric("Alpha", str(values.get("Alpha", "-")))
    cards2[1].metric("Delta", str(values.get("Delta", "-")))
    cards2[2].metric("Expected Remaining Hours", str(values.get("Expected Remaining Hours", "-")))
    st.caption(
        f"{values.get('Interpretation', 'Published synchronized values')} • "
        f"Run {str(values.get('Run ID', '-'))[:18]} • Latest H1 {str(values.get('Latest Completed H1', '-'))[:25]}"
    )

    tables = collect_existing_regime_tables(result, state=state)
    if len(tables) < 2:
        st.info(
            "Medium and Higher Standard regime tables are not present in the completed generation. "
            "Open Settings → Errors / Fix Fast for the real calculation status."
        )
    available = {title: frame for title, frame in tables}
    for title, key_prefix in (
        ("Medium Standard Regime — About 5 Days", "medium_standard"),
        ("Higher Standard Regime — About 25 Days", "higher_standard"),
    ):
        st.markdown(f"##### {title}")
        frame = available.get(title)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            st.warning(f"{title} is unavailable in this published generation.")
            continue
        _render_standard_table(title, frame, key_prefix=key_prefix)


__all__ = [
    "build_existing_regime_summary",
    "collect_existing_regime_tables",
    "render_existing_regime_inner_section",
]
