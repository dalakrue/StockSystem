"""Aggregate Field 3 section for every loaded symbol.

This surface deliberately ignores the active display symbol.  The global
selector changes selected-symbol details across Field 3/13, while these four
aggregate tables always retain the full successfully completed universe.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import pandas as pd
import numpy as np
from core.global_symbol_context import get_global_symbol_context
from ui.field3_mobile_cards_20260722 import is_phone_mode, render_responsive_records
from core.regime_age_columns_20260722 import (
    CANDLE_AGE_COLUMN,
    RECENT_CHANGE_RANK_COLUMN,
    REGIME_START_AGE_RANK_COLUMN,
    REGIME_START_STANDARD_COLUMN,
    STANDARD_AGE_COLUMNS,
    enrich_evidence,
    enrich_ranking,
)

AGE_ONLY_RANK_COLUMN = "Regime Age Rank"
MIDDLE_AGE_RANK_COLUMN = "Avg Regime Candle Rank"
MIDDLE_AGE_DISPLAY_COLUMN = "Middle Candle After Regime Start"
MIDDLE_AVG_SOURCE_COLUMN = "Middle Avg Regime Candle Count Before Regime Change"
AVG_REGIME_CANDLE_COLUMN = "Avg Regime Candle Count Before Regime Change"
CANDLE_STATISTICS_COLUMN = "Regime Maturity Score"
MIDDLE_COMPLETED_SAMPLE_COLUMN = "Middle Completed Regime Sample Count"
COMPLETED_SAMPLE_DISPLAY_COLUMN = "Completed Regime Samples"
MIDDLE_NUMERIC_HIGHLIGHT_COLUMNS = [
    CANDLE_AGE_COLUMN,
    CANDLE_STATISTICS_COLUMN,
    AVG_REGIME_CANDLE_COLUMN,
    COMPLETED_SAMPLE_DISPLAY_COLUMN,
]
STANDARD_LABELS = {
    "LOWER": "Lower Standard Summary",
    "MIDDLE": "Middle Standard Summary",
    "HIGHER": "Higher Standard Summary",
}


def _load_saved_if_needed(state: MutableMapping[str, Any]) -> None:
    ranking = state.get("field3_multisymbol_regime_20260708")
    evidence = state.get("field3_regime_evidence_v2")
    if isinstance(ranking, pd.DataFrame) and not ranking.empty and isinstance(evidence, pd.DataFrame) and not evidence.empty:
        return
    try:
        from core.field3_three_regime_engine import load_saved_field3_v2
        load_saved_field3_v2(state)
    except Exception as exc:
        state["field3_summary_reload_error_20260722"] = f"{type(exc).__name__}: {exc}"


def _scope_to_loaded(frame: pd.DataFrame, loaded: list[str]) -> pd.DataFrame:
    if frame.empty or "Symbol" not in frame.columns or not loaded:
        return frame.copy()
    allowed = {str(symbol).upper() for symbol in loaded}
    return frame.loc[frame["Symbol"].astype(str).str.upper().isin(allowed)].copy()


def _standard_table(evidence: pd.DataFrame, ranking: pd.DataFrame, standard: str) -> pd.DataFrame:
    scoped = evidence.loc[evidence.get("Standard", pd.Series("", index=evidence.index)).astype(str).str.upper().eq(standard)].copy()
    if scoped.empty:
        return scoped
    current_rank = ranking[[c for c in ("Symbol", "Rank") if c in ranking.columns]].copy()
    if set(current_rank.columns) == {"Symbol", "Rank"}:
        scoped = scoped.merge(current_rank.rename(columns={"Rank": "Final Rank"}), on="Symbol", how="left")
    age = pd.to_numeric(scoped[CANDLE_AGE_COLUMN], errors="coerce")
    scoped[REGIME_START_AGE_RANK_COLUMN] = age.rank(method="min", ascending=False, na_option="bottom").astype("Int64")
    scoped[RECENT_CHANGE_RANK_COLUMN] = age.rank(method="min", ascending=True, na_option="bottom").astype("Int64")
    columns = [
        REGIME_START_AGE_RANK_COLUMN, RECENT_CHANGE_RANK_COLUMN, "Final Rank", "Symbol", "Regime State", "Bias",
        "Posterior Probability", "Persistence Probability", "Expected Duration", CANDLE_AGE_COLUMN,
        "Changepoint Probability", "Transition Risk", "Calibrated Reliability", "Sample Count",
        "Data Quality Grade", "Completed Candle",
    ]
    table = scoped[[c for c in columns if c in scoped.columns]].copy()
    sort_cols = [c for c in (RECENT_CHANGE_RANK_COLUMN, "Final Rank", "Symbol") if c in table.columns]
    return table.sort_values(sort_cols, kind="mergesort").reset_index(drop=True) if sort_cols else table.reset_index(drop=True)



def _age_only_ranking(ranking: pd.DataFrame) -> pd.DataFrame:
    """Rank symbols only by how recently the Higher regime started.

    Rank 1 is the newest regime change (smallest completed-candle age). No
    probability, reliability or composite score is allowed to change the order.
    """
    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        return pd.DataFrame()
    higher_age_column = STANDARD_AGE_COLUMNS["HIGHER"]
    columns = [c for c in (
        "Symbol", higher_age_column, CANDLE_AGE_COLUMN, REGIME_START_STANDARD_COLUMN,
        "Lower Regime", "Lower Bias", "Middle Regime", "Middle Bias",
        "Higher Regime", "Higher Bias", "Completed Candle", "Timeframe",
    ) if c in ranking.columns]
    source_age = higher_age_column if higher_age_column in columns else CANDLE_AGE_COLUMN
    if "Symbol" not in columns or source_age not in columns:
        return pd.DataFrame()
    table = ranking[columns].copy()
    table[CANDLE_AGE_COLUMN] = pd.to_numeric(table[source_age], errors="coerce")
    table = table.dropna(subset=[CANDLE_AGE_COLUMN]).drop_duplicates(subset=["Symbol"], keep="first")
    if table.empty:
        return table
    table[AGE_ONLY_RANK_COLUMN] = table[CANDLE_AGE_COLUMN].rank(
        method="min", ascending=True, na_option="bottom"
    ).astype("Int64")
    ordered = [
        AGE_ONLY_RANK_COLUMN, "Symbol", CANDLE_AGE_COLUMN,
        "Lower Regime", "Lower Bias", "Middle Regime", "Middle Bias",
        "Higher Regime", "Higher Bias",
        REGIME_START_STANDARD_COLUMN, "Completed Candle", "Timeframe",
    ]
    table = table[[c for c in ordered if c in table.columns]]
    table = table.rename(columns={
        "Higher Regime": "Higher Standard Regime State",
        "Higher Bias": "Higher Standard Regime Bias",
        "Middle Regime": "Middle Standard Regime State",
        "Middle Bias": "Middle Regime Bias",
        "Lower Regime": "Lower Standard Regime State",
        "Lower Bias": "Lower Regime Bias",
    })
    return table.sort_values([AGE_ONLY_RANK_COLUMN, "Symbol"], kind="mergesort").reset_index(drop=True)
def _middle_age_ranking(ranking: pd.DataFrame) -> pd.DataFrame:
    """
    Rank symbols by current Middle regime candle age.

    Rank 1 = newest Middle regime start.
    Smaller Candle After Regime Start means a more recent regime change.
    """
    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        return pd.DataFrame()

    middle_age_column = STANDARD_AGE_COLUMNS["MIDDLE"]
    columns = [
        c for c in (
            "Symbol",
            middle_age_column,

            # Restore historical average Middle regime data
            MIDDLE_AVG_SOURCE_COLUMN,
            MIDDLE_COMPLETED_SAMPLE_COLUMN,

            "Lower Regime",
            "Lower Bias",
            "Middle Regime",
            "Middle Bias",
            "Higher Regime",
            "Higher Bias",
            "Completed Candle",
            "Timeframe",
        )
        if c in ranking.columns
    ]

    if "Symbol" not in columns or middle_age_column not in columns:
        return pd.DataFrame()

    table = ranking[columns].copy()

    # Current Middle regime candle age
    table[CANDLE_AGE_COLUMN] = pd.to_numeric(
        table[middle_age_column],
        errors="coerce"
    )
# Restore display columns
    if MIDDLE_AVG_SOURCE_COLUMN in table.columns:
        table[AVG_REGIME_CANDLE_COLUMN] = pd.to_numeric(
            table[MIDDLE_AVG_SOURCE_COLUMN],
            errors="coerce"
        ).round(2)

    if MIDDLE_COMPLETED_SAMPLE_COLUMN in table.columns:
        table[COMPLETED_SAMPLE_DISPLAY_COLUMN] = pd.to_numeric(
            table[MIDDLE_COMPLETED_SAMPLE_COLUMN],
            errors="coerce"
        ).astype("Int64")


    if AVG_REGIME_CANDLE_COLUMN in table.columns:

        avg_candles = pd.to_numeric(
            table[AVG_REGIME_CANDLE_COLUMN],
            errors="coerce"
        )

        sample_count = pd.to_numeric(
            table[COMPLETED_SAMPLE_DISPLAY_COLUMN],
            errors="coerce"
        )

        table[CANDLE_STATISTICS_COLUMN] = (
            table[CANDLE_AGE_COLUMN]
            .div(avg_candles)
            .mul(np.log1p(sample_count))
            .where(
                (avg_candles > 0) &
                (sample_count > 0)
            )
            .round(2)
        )
    table = (
        table
        .dropna(subset=[CANDLE_AGE_COLUMN])
        .drop_duplicates(subset=["Symbol"], keep="first")
    )

    if table.empty:
        return table

    # Rank by newest Middle regime start
    # Smaller candle age = Rank 1
    table[MIDDLE_AGE_RANK_COLUMN] = (
        table[CANDLE_AGE_COLUMN]
        .rank(method="min", ascending=True)
        .astype("Int64")
    )

    ordered = [
        MIDDLE_AGE_RANK_COLUMN,
        "Symbol",
        "Lower Bias",
        "Middle Bias",
        "Higher Bias",
        CANDLE_AGE_COLUMN,
        CANDLE_STATISTICS_COLUMN,

        AVG_REGIME_CANDLE_COLUMN,
        COMPLETED_SAMPLE_DISPLAY_COLUMN,
    
        "Middle Regime",
  
        "Lower Regime",

        "Higher Regime",

        "Completed Candle",
        "Timeframe",
    ]

    table = table[[c for c in ordered if c in table.columns]]

    table = table.rename(columns={
        "Middle Regime": "Middle Standard Regime State",
        "Middle Bias": "Middle Regime Bias",
        "Lower Regime": "Lower Standard Regime State",
        "Lower Bias": "Lower Regime Bias",
        "Higher Regime": "Higher Standard Regime State",
        "Higher Bias": "Higher Standard Regime Bias",
    })

    return (
        table
        .sort_values(
            [MIDDLE_AGE_RANK_COLUMN, "Symbol"],
            ascending=[True, True],
            kind="mergesort"
        )
        .reset_index(drop=True)
    )
def _middle_regime_extreme_highlights(
    middle_age: pd.DataFrame,
) -> tuple[dict[str, set[Any]], set[Any]]:
    """
    Find smallest/largest numeric values for each Middle Regime column
    and identify rows where Middle Bias == Higher Standard Regime Bias.

    Returns:
        cell_extremes:
            {
                "column": {
                    ("min", value),
                    ("max", value),
                }
            }

        matching_rows:
            index values of rows where Middle Bias == Higher Bias
    """
    if not isinstance(middle_age, pd.DataFrame) or middle_age.empty:
        return {}, set()

    cell_extremes: dict[str, set[Any]] = {}

    for column in MIDDLE_NUMERIC_HIGHLIGHT_COLUMNS:
        if column not in middle_age.columns:
            continue

        values = pd.to_numeric(
            middle_age[column],
            errors="coerce",
        ).dropna()

        if values.empty:
            continue

        minimum = values.min()
        maximum = values.max()

        cell_extremes[column] = {
            ("min", minimum),
            ("max", maximum),
        }

    matching_rows: set[Any] = set()

    if (
        "Middle Regime Bias" in middle_age.columns
        and "Higher Standard Regime Bias" in middle_age.columns
    ):
        middle_bias = (
            middle_age["Middle Regime Bias"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        higher_bias = (
            middle_age["Higher Standard Regime Bias"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matching_rows = set(
            middle_age.index[middle_bias.eq(higher_bias)]
        )

    return cell_extremes, matching_rows
def render_middle_regime_download_button(
    st: Any,
    middle_age: pd.DataFrame
) -> None:
    """
    Render CSV download for Middle Regime Age Ranking.
    """

    if not isinstance(middle_age, pd.DataFrame):
        return

    if middle_age.empty:
        return

    csv = middle_age.to_csv(
        index=False,
        encoding="utf-8"
    )

    st.download_button(
        label="📥 Download Middle Standard Regime Ranking CSV",
        data=csv,
        file_name="middle_standard_regime_ranking.csv",
        mime="text/csv",
        key="download_middle_standard_regime_csv",
        use_container_width=True,
    )
def render_multisymbol_regime_summary(st: Any, state: MutableMapping[str, Any]) -> None:
    _load_saved_if_needed(state)
    context = get_global_symbol_context(state)
    loaded = list(context.completed_symbols or context.loaded_symbols)
    raw_ranking = state.get("field3_multisymbol_regime_20260708")
    raw_evidence = state.get("field3_regime_evidence_v2")
    if not isinstance(raw_ranking, pd.DataFrame) or raw_ranking.empty:
        st.info("No completed multi-symbol Field 3 generation is available. Select and load symbols in Settings, then run Super Quick, Quick, or Full Calculation.")
        return
    full_evidence = enrich_evidence(raw_evidence if isinstance(raw_evidence, pd.DataFrame) else pd.DataFrame())
    full_ranking = enrich_ranking(raw_ranking, full_evidence)
    # Publish enriched canonical copies, but never replace them with a display
    # filter. The aggregate scope is local and cannot affect selector identity.
    state["field3_multisymbol_regime_20260708"] = full_ranking
    state["field3_regime_evidence_v2"] = full_evidence
    ranking = _scope_to_loaded(full_ranking, loaded)
    evidence = _scope_to_loaded(full_evidence, loaded)

    st.markdown("## All Loaded Symbols — Three Standards and Final Ranking")
    st.caption(
        "This aggregate section always shows the complete loaded/completed universe and is intentionally independent of the active Global Symbol. "
        "Candle After Regime Start is measured in completed candles. In the Regime Age Ranking, Rank 1 means the newest/recent regime change (the smallest candle age)."
    )
    phone_mode = is_phone_mode(state)
    metrics = st.columns(2 if phone_mode else 5)
    displayed_timeframe = context.timeframe or (
        str(ranking["Timeframe"].iloc[0]) if not ranking.empty and "Timeframe" in ranking.columns else "—"
    )
    if phone_mode:
        metrics[0].metric("Loaded", len(loaded) if loaded else len(ranking))
        metrics[1].metric("Timeframe", displayed_timeframe)
        st.caption(f"Ranking rows: {len(ranking)} · Standard rows: {len(evidence)} · Generation: {context.generation or '—'}")
    else:
        metrics[0].metric("Loaded / Completed", len(loaded) if loaded else len(ranking))
        metrics[1].metric("Ranking Rows", len(ranking))
        metrics[2].metric("Standard Rows", len(evidence))
        metrics[3].metric("Timeframe", displayed_timeframe)
        metrics[4].metric("Generation", context.generation or "—")
    if loaded:
        st.caption("Aggregate universe: " + " → ".join(loaded))

    st.markdown("### Regime Age Ranking — Candle After Regime Start Only")
    st.caption(
        "This ranking uses only the Higher regime candle age. Rank 1 is the most recent Higher regime change (smallest candle count). Lower, Middle, and Higher bias columns are context only and never affect the rank."
    )
    age_only = _age_only_ranking(ranking)
    if age_only.empty:
        st.info("Candle-after-regime-start values are not available yet for the completed universe.")
    else:
        st.caption(
            "Color key: green = Top 5, red = Last 5, blue whole row = Lower, Middle, and Higher regime bias are all the same."
        )
        render_responsive_records(
            st, state, age_only,
            preferred_columns=[
                AGE_ONLY_RANK_COLUMN, "Symbol", CANDLE_AGE_COLUMN,
                "Higher Standard Regime State", "Higher Standard Regime Bias",
                "Middle Standard Regime State", "Middle Regime Bias",
                "Lower Standard Regime State", "Lower Regime Bias",
                REGIME_START_STANDARD_COLUMN,
            ],
            rank_column=AGE_ONLY_RANK_COLUMN,
            desktop_height=min(620, 100 + 38 * len(age_only)),
            full_table_label="Full Regime Age table",
            visualize_rank_bands=True,
            match_columns=("Lower Regime Bias", "Middle Regime Bias", "Higher Standard Regime Bias"),
            highlight_match_row=True,
            max_phone_rows=30,
        )
   
    st.markdown("### Middle Regime Age Ranking — Candle After Middle Regime Start Only")
    st.caption(
        "Rank 1 is the newest Middle regime start (smallest Candle After Regime Start value). "
        "Candle After Regime Start is the only ranking factor. Bias columns are display context and never change the rank."
    )
    middle_age = _middle_age_ranking(ranking)
    middle_cell_extreme_columns = [
        CANDLE_AGE_COLUMN,
        CANDLE_STATISTICS_COLUMN,
        AVG_REGIME_CANDLE_COLUMN,
        COMPLETED_SAMPLE_DISPLAY_COLUMN,
    ]
    if middle_age.empty:
        st.info("Middle regime-age values are not available yet for the completed universe.")
    else:
        render_middle_regime_download_button(st, middle_age)
        st.caption(
            st.caption(
            "Color key: green cell = smallest numeric value, "
            "red cell = largest numeric value, "
            "blue whole row = Middle Regime Bias matches Higher Standard Regime Bias. "
            "Top 5 and Last 5 row bands are also shown."
        )
        )
        render_responsive_records(
            st,
            state,
            middle_age,
            preferred_columns=[
                MIDDLE_AGE_RANK_COLUMN,
                "Symbol",
                "Lower Regime Bias",
                "Middle Regime Bias",
                "Higher Standard Regime Bias",
                CANDLE_AGE_COLUMN,
                CANDLE_STATISTICS_COLUMN,
                AVG_REGIME_CANDLE_COLUMN,
                COMPLETED_SAMPLE_DISPLAY_COLUMN,
                "Middle Standard Regime State",
                "Lower Standard Regime State",
                "Higher Standard Regime State",
            ],
            rank_column=MIDDLE_AGE_RANK_COLUMN,
            desktop_height=min(620, 100 + 38 * len(middle_age)),
            full_table_label="Full Middle Regime Age table",
            visualize_rank_bands=True,

            # Whole-row match:
            match_columns=(
                "Middle Regime Bias",
                "Higher Standard Regime Bias",
            ),
            highlight_match_row=True,

            # Numeric min/max visualization:
            cell_extreme_highlights=middle_cell_extreme_columns,
            highlight_min_cells=True,
            highlight_max_cells=True,

            max_phone_rows=30,
        )



    fast_two_table_mode = bool(state.get("field3_fast_two_table_mode_20260722")) or str(
        state.get("field3_last_run_scope_20260722") or ""
    ).upper() == "LUNCH_CORE"
    standards_to_render = (("HIGHER", STANDARD_LABELS["HIGHER"]),) if fast_two_table_mode else tuple(STANDARD_LABELS.items())
    for standard, label in standards_to_render:
        st.markdown(f"### {label}")
        table = _standard_table(evidence, ranking, standard)
        if table.empty:
            st.info(f"No saved {standard.title()} evidence is available for the completed universe.")
        else:
            render_responsive_records(
                st, state, table,
                preferred_columns=[
                    RECENT_CHANGE_RANK_COLUMN, "Symbol", "Regime State", "Bias",
                    CANDLE_AGE_COLUMN, "Calibrated Reliability", "Posterior Probability",
                    "Transition Risk", "Data Quality Grade",
                ],
                rank_column=RECENT_CHANGE_RANK_COLUMN,
                desktop_height=min(520, 92 + 38 * len(table)),
                full_table_label=f"Full {label} table",
            )

    if fast_two_table_mode:
        st.caption("Super Quick intentionally stops after these three compact sections. Click Quick Run to calculate the deferred Lower/Middle summary tables, final cross-symbol ranking, Field 10/11, AI, research, and trust-history work.")
        return

    st.markdown("### Final Cross-Symbol Ranking")
    final_columns = [
        "Rank", REGIME_START_AGE_RANK_COLUMN, RECENT_CHANGE_RANK_COLUMN, "Symbol",
        "Lower Regime", "Lower Bias", "Lower Probability", "Lower Reliability",
        "Middle Regime", "Middle Bias", "Middle Probability", "Middle Reliability",
        "Higher Regime", "Higher Bias", "Higher Probability", "Higher Reliability",
        CANDLE_AGE_COLUMN, REGIME_START_STANDARD_COLUMN,
        "Three-Regime Agreement", "Composite Bias", "Composite Score", "Decision Strength",
        "Calibrated Reliability", "Entry Permission", "Block Reason", "Completed Candle",
    ]
    final = ranking[[c for c in final_columns if c in ranking.columns]].copy()
    if "Rank" in final.columns:
        final = final.sort_values("Rank", kind="mergesort")
    render_responsive_records(
        st, state, final,
        preferred_columns=[
            "Rank", "Symbol", "Higher Regime", "Higher Bias", CANDLE_AGE_COLUMN,
            "Composite Bias", "Composite Score", "Decision Strength",
            "Calibrated Reliability", "Entry Permission", "Block Reason",
        ],
        rank_column="Rank",
        desktop_height=min(720, 100 + 38 * len(final)),
        full_table_label="Full Cross-Symbol Ranking table",
        visualize_rank_bands=True,
        match_columns=("Higher Regime", "Middle Regime"),
        max_phone_rows=30,
    )


__all__ = [
    "render_multisymbol_regime_summary", "_age_only_ranking", "_middle_age_ranking",
    "AGE_ONLY_RANK_COLUMN", "MIDDLE_AGE_RANK_COLUMN", "MIDDLE_AGE_DISPLAY_COLUMN",
    "MIDDLE_AVG_SOURCE_COLUMN", "AVG_REGIME_CANDLE_COLUMN",
    "MIDDLE_COMPLETED_SAMPLE_COLUMN", "COMPLETED_SAMPLE_DISPLAY_COLUMN",
    "CANDLE_STATISTICS_COLUMN",
]
