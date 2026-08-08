"""Responsive Field 3 record cards for narrow phone screens.

Desktop keeps the complete Streamlit dataframe. Phone mode presents the most
important values as stacked cards so an iPhone-width screen never requires the
user to swipe across dozens of columns. The complete table remains available in
one collapsed expander for audit/export use.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

import pandas as pd


def is_phone_mode(state: Mapping[str, Any]) -> bool:
    return bool(
        state.get("phone_mode")
        or state.get("extreme_mobile_lite_mode_20260628")
        or str(state.get("mobile_ui_mode_20260628") or "").strip().lower() == "phone"
    )


def _display(value: Any) -> str:
    if value is None or value is pd.NA:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except Exception:
        pass
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def inject_field3_mobile_card_css(st: Any) -> None:
    st.markdown(
        """
<style id="field3-mobile-cards-20260722">
.f3-phone-card {
  width:100%; box-sizing:border-box; margin:.42rem 0; padding:.68rem;
  border:1px solid rgba(14,116,144,.20); border-radius:14px;
  background:linear-gradient(145deg,rgba(255,255,255,.94),rgba(239,248,255,.86));
  box-shadow:0 4px 13px rgba(2,132,199,.07); overflow:hidden;
}
.f3-phone-card.f3-top-five {
  border-color:rgba(22,163,74,.45);
  background:linear-gradient(145deg,rgba(240,253,244,.98),rgba(220,252,231,.90));
}
.f3-phone-card.f3-last-five {
  border-color:rgba(220,38,38,.38);
  background:linear-gradient(145deg,rgba(254,242,242,.98),rgba(254,226,226,.88));
}
.f3-phone-card.f3-regime-match .f3-phone-symbol {
  color:#1d4ed8; padding:.18rem .42rem; border-radius:999px;
  background:rgba(191,219,254,.88); box-shadow:0 0 0 1px rgba(37,99,235,.18);
}
.f3-phone-card.f3-full-row-match {
  border-color:rgba(37,99,235,.48);
  background:linear-gradient(145deg,rgba(239,246,255,.99),rgba(219,234,254,.92));
  box-shadow:0 5px 15px rgba(37,99,235,.12);
}
.f3-phone-card.f3-full-row-match .f3-phone-symbol {
  color:#1e3a8a;
}
.f3-phone-head {display:flex; align-items:center; justify-content:space-between; gap:.5rem; margin-bottom:.5rem;}
.f3-phone-symbol {font-weight:900; font-size:1rem; color:#0f172a; overflow-wrap:anywhere;}
.f3-phone-rank {font-weight:900; font-size:.76rem; padding:.22rem .5rem; border-radius:999px;
  background:rgba(186,230,253,.82); color:#075985; white-space:nowrap;}
.f3-phone-grid {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.42rem .55rem;}
.f3-phone-item {min-width:0; padding:.38rem .42rem; border-radius:10px; background:rgba(255,255,255,.72);}
.f3-phone-label {font-size:.64rem; line-height:1.15; font-weight:800; color:#64748b; margin-bottom:.16rem;
  overflow-wrap:anywhere;}
.f3-phone-value {font-size:.79rem; line-height:1.25; font-weight:800; color:#0f172a; overflow-wrap:anywhere; word-break:break-word;}
@media (max-width:390px) {
  .f3-phone-card {padding:.58rem;}
  .f3-phone-grid {gap:.36rem;}
  .f3-phone-label {font-size:.61rem;}
  .f3-phone-value {font-size:.75rem;}
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_responsive_records(
    st: Any,
    state: Mapping[str, Any],
    frame: pd.DataFrame,
    *,
    preferred_columns: Sequence[str],
    rank_column: str | None = "Rank",
    symbol_column: str = "Symbol",
    desktop_height: int | None = None,
    full_table_label: str = "Full table — swipe only when needed",
    max_phone_rows: int = 24,
    visualize_rank_bands: bool = False,
    match_columns: Sequence[str] | None = None,
    highlight_match_row: bool = False,
    cell_extreme_highlights: Sequence[str] | None = None,
    highlight_min_cells: bool = False,
    highlight_max_cells: bool = False,
) -> None:
    """Render a dataframe on desktop or no-horizontal-scroll cards on phone."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return

    def _matching_positions() -> set[int]:
        columns = tuple(match_columns or ())
        if len(columns) < 2 or any(column not in frame.columns for column in columns):
            return set()
        normalized = [frame[column].astype(str).str.strip().str.upper() for column in columns]
        invalid = {"", "NAN", "NONE", "UNAVAILABLE", "UNKNOWN", "BLOCKED", "DEFERRED", "DEFERRED_TO_QUICK"}
        valid = pd.Series(True, index=frame.index)
        for values in normalized:
            valid &= ~values.isin(invalid)
        matched = valid.copy()
        anchor = normalized[0]
        for values in normalized[1:]:
            matched &= anchor.eq(values)
        return {position for position, is_match in enumerate(matched.tolist()) if bool(is_match)}

    matching_positions = _matching_positions()
    top_positions = set(range(min(5, len(frame)))) if visualize_rank_bands else set()
    bottom_positions = set(range(max(0, len(frame) - 5), len(frame))) if visualize_rank_bands else set()
    def _styled_table() -> Any:
        styles = pd.DataFrame(
            "",
            index=frame.index,
            columns=frame.columns,
        )

        # --------------------------------------------------
        # 1. Existing Top-5 / Last-5 row visualization
        # --------------------------------------------------

        for position in top_positions:
            styles.iloc[position, :] = (
                "background-color:#dcfce7;"
                "color:#14532d;"
                "font-weight:700"
            )

        for position in bottom_positions - top_positions:
            styles.iloc[position, :] = (
                "background-color:#fee2e2;"
                "color:#7f1d1d;"
                "font-weight:700"
            )

        # --------------------------------------------------
        # 2. Whole-row bias match
        #
        # Middle Bias == Higher Standard Regime Bias
        # --------------------------------------------------

        if highlight_match_row:
            for position in matching_positions:
                styles.iloc[position, :] = (
                    "background-color:#dbeafe;"
                    "color:#1e3a8a;"
                    "font-weight:900;"
                    "border-top:1px solid #60a5fa;"
                    "border-bottom:1px solid #60a5fa"
                )

        elif symbol_column in frame.columns:
            symbol_index = frame.columns.get_loc(symbol_column)

            for position in matching_positions:
                styles.iloc[position, symbol_index] = (
                    "background-color:#bfdbfe;"
                    "color:#1e3a8a;"
                    "font-weight:900;"
                    "border:1px solid #60a5fa"
                )

        # --------------------------------------------------
        # 3. Smallest / largest numeric values
        # --------------------------------------------------

        extreme_columns = tuple(cell_extreme_highlights or ())

        for column in extreme_columns:

            if column not in frame.columns:
                continue

            values = pd.to_numeric(
                frame[column],
                errors="coerce",
            )

            valid_values = values.dropna()

            if valid_values.empty:
                continue

            minimum = valid_values.min()
            maximum = valid_values.max()

            # Smallest value
            if highlight_min_cells:
                minimum_positions = [
                    position
                    for position, value in enumerate(values)
                    if pd.notna(value) and value == minimum
                ]

                for position in minimum_positions:
                    styles.iloc[position, frame.columns.get_loc(column)] = (
                        "background-color:#bbf7d0;"
                        "color:#14532d;"
                        "font-weight:900;"
                    )

            # Largest value
            if highlight_max_cells:
                maximum_positions = [
                    position
                    for position, value in enumerate(values)
                    if pd.notna(value) and value == maximum
                ]

                for position in maximum_positions:
                    styles.iloc[position, frame.columns.get_loc(column)] = (
                        "background-color:#fecaca;"
                        "color:#991b1b;"
                        "font-weight:900;"
                    )

        try:
            return frame.style.apply(
                lambda _: styles,
                axis=None,
            )
        except Exception:
            return frame
    def _apply_middle_regime_styles(
        dataframe: pd.DataFrame,
        numeric_columns: list[str],
        match_columns: tuple[str, str],
    ) -> pd.DataFrame:
        styles = pd.DataFrame(
            "",
            index=dataframe.index,
            columns=dataframe.columns,
        )

        # --------------------------------------------------
        # 1. Whole-row highlighting
        # --------------------------------------------------

        if all(column in dataframe.columns for column in match_columns):
            left = (
                dataframe[match_columns[0]]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            right = (
                dataframe[match_columns[1]]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            matching_rows = left.eq(right)

            styles.loc[matching_rows, :] = (
                "background-color: #dbeafe;"
            )

        # --------------------------------------------------
        # 2. Smallest / largest numeric values
        # --------------------------------------------------

        for column in numeric_columns:

            if column not in dataframe.columns:
                continue

            values = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

            valid = values.dropna()

            if valid.empty:
                continue

            minimum = valid.min()
            maximum = valid.max()

            min_rows = values.eq(minimum)
            max_rows = values.eq(maximum)

            # Minimum = green
            styles.loc[min_rows, column] = (
                "background-color: #bbf7d0;"
                "font-weight: 700;"
            )

            # Maximum = red
            styles.loc[max_rows, column] = (
                "background-color: #fecaca;"
                "font-weight: 700;"
            )

        return styles
    def _style_middle_extremes(
        dataframe: pd.DataFrame,
        numeric_columns: list[str],
    ):
        styled = dataframe.style

        for column in numeric_columns:
            if column not in dataframe.columns:
                continue

            values = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

            if values.dropna().empty:
                continue

            minimum = values.min()
            maximum = values.max()

            min_mask = values.eq(minimum)
            max_mask = values.eq(maximum)

            def color_minimum(row):
                styles = [""] * len(row)

                if min_mask.loc[row.name]:
                    styles[row.index.get_loc(column)] = (
                        "background-color: #d9f2d9;"
                    )

                return styles

            def color_maximum(row):
                styles = [""] * len(row)

                if max_mask.loc[row.name]:
                    styles[row.index.get_loc(column)] = (
                        "background-color: #ffd6d6;"
                    )

                return styles

            styled = styled.apply(color_minimum, axis=1)
            styled = styled.apply(color_maximum, axis=1)

        return styled
    if not is_phone_mode(state):
        kwargs = {"use_container_width": True, "hide_index": True}
        if desktop_height is not None:
            kwargs["height"] = int(desktop_height)
        st.dataframe(_styled_table(), **kwargs)
        return

    inject_field3_mobile_card_css(st)
    columns = [column for column in preferred_columns if column in frame.columns]
    if symbol_column in frame.columns and symbol_column not in columns:
        columns.insert(0, symbol_column)
    if rank_column and rank_column in frame.columns and rank_column not in columns:
        columns.insert(0, rank_column)
    compact = frame.loc[:, columns].head(max_phone_rows).copy() if columns else frame.head(max_phone_rows).copy()
    extreme_columns = tuple(cell_extreme_highlights or ())

    column_extremes: dict[str, tuple[float | None, float | None]] = {}

    for column in extreme_columns:
        if column not in compact.columns:
            continue

        values = pd.to_numeric(
            compact[column],
            errors="coerce",
        )

        valid_values = values.dropna()

        if valid_values.empty:
            continue

        column_extremes[column] = (
            valid_values.min(),
            valid_values.max(),
        )
    blocks: list[str] = []
    for position, (_, row) in enumerate(compact.iterrows(), start=1):
        zero_position = position - 1
        symbol = _display(row.get(symbol_column, f"Row {position}"))
        rank_value = _display(row.get(rank_column)) if rank_column and rank_column in compact.columns else str(position)
        items: list[str] = []
        for column in compact.columns:
            if column in {symbol_column, rank_column}:
                continue
            value = row.get(column)
            value_text = _display(value)

            item_class = "f3-phone-item"
            value_class = "f3-phone-value"

            if column in column_extremes:
                numeric_value = pd.to_numeric(
                    pd.Series([value]),
                    errors="coerce",
                ).iloc[0]

                minimum, maximum = column_extremes[column]

                if (
                    highlight_min_cells
                    and pd.notna(numeric_value)
                    and numeric_value == minimum
                ):
                    value_class += " f3-min-value"

                elif (
                    highlight_max_cells
                    and pd.notna(numeric_value)
                    and numeric_value == maximum
                ):
                    value_class += " f3-max-value"

            items.append(
                '<div class="f3-phone-item">'
                f'<div class="f3-phone-label">{escape(str(column))}</div>'
                f'<div class="{value_class}">{escape(value_text)}</div>'
                '</div>'
            )
        card_classes = ["f3-phone-card"]
        if zero_position in top_positions:
            card_classes.append("f3-top-five")
        elif zero_position in bottom_positions:
            card_classes.append("f3-last-five")
        if zero_position in matching_positions:
            card_classes.append("f3-full-row-match" if highlight_match_row else "f3-regime-match")
        blocks.append(
            f'<div class="{" ".join(card_classes)}">'
            '<div class="f3-phone-head">'
            f'<div class="f3-phone-symbol">{escape(symbol)}</div>'
            f'<div class="f3-phone-rank">Rank {escape(rank_value)}</div>'
            '</div>'
            f'<div class="f3-phone-grid">{"".join(items)}</div>'
            '</div>'
        )
    st.markdown("".join(blocks), unsafe_allow_html=True)
    if len(frame) > max_phone_rows:
        st.caption(f"Showing the first {max_phone_rows} rows in phone cards.")
    with st.expander(full_table_label, expanded=False):
        kwargs = {"use_container_width": True, "hide_index": True}
        if desktop_height is not None:
            kwargs["height"] = int(desktop_height)
        st.dataframe(_styled_table(), **kwargs)


__all__ = ["is_phone_mode", "inject_field3_mobile_card_css", "render_responsive_records"]
