"""Table-only Field 3 renderer.

The former mobile-card renderer duplicated Field 3 output and carried a large
amount of phone-only HTML/CSS.  Field 3 now has one canonical table renderer
for every device.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


def render_field3_table(
    st: Any,
    state: Mapping[str, Any],
    frame: pd.DataFrame,
    *,
    preferred_columns: Sequence[str] = (),
    rank_column: str | None = "Rank",
    symbol_column: str = "Symbol",
    desktop_height: int | None = None,
    full_table_label: str = "Full table",
    visualize_rank_bands: bool = False,
    match_columns: Sequence[str] | None = None,
    highlight_match_row: bool = False,
    cell_extreme_highlights: Sequence[str] | None = None,
    highlight_min_cells: bool = False,
    highlight_max_cells: bool = False,
    column_config: Mapping[str, Any] | None = None,
) -> None:
    """Render one canonical dataframe with the existing desktop highlights."""
    del state, preferred_columns, rank_column, full_table_label
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return

    frame = frame.loc[:, ~frame.columns.duplicated(keep="last")].copy()
    # The symbol is the primary lookup key for both Middle Standard Ranking
    # and Finder. Keep it as the first visible column instead of letting the
    # Strategy Decision column jump ahead of it.
    ordered = []
    if symbol_column in frame.columns:
        ordered.append(symbol_column)
    # Keep operational status columns immediately after Symbol when present.
    for column in ("SL", "Strategy Decision", "Weighted Risk Decision"):
        if column in frame.columns and column not in ordered:
            ordered.append(column)
    frame = frame.loc[:, ordered + [c for c in frame.columns if c not in ordered]]

    styles = pd.DataFrame("", index=frame.index, columns=frame.columns)
    if visualize_rank_bands:
        for pos in range(min(5, len(frame))):
            styles.iloc[pos, :] = "background-color:#dcfce7;color:#14532d;font-weight:700"
        for pos in range(max(0, len(frame) - 5), len(frame)):
            if pos >= min(5, len(frame)):
                styles.iloc[pos, :] = "background-color:#fee2e2;color:#7f1d1d;font-weight:700"

    columns = tuple(match_columns or ())
    if len(columns) >= 2 and all(c in frame.columns for c in columns):
        normalized = [frame[c].astype(str).str.strip().str.upper() for c in columns]
        invalid = {"", "NAN", "NONE", "UNAVAILABLE", "UNKNOWN", "BLOCKED", "DEFERRED", "DEFERRED_TO_QUICK"}
        matched = pd.Series(True, index=frame.index)
        for values in normalized:
            matched &= ~values.isin(invalid)
        anchor = normalized[0]
        for values in normalized[1:]:
            matched &= anchor.eq(values)
        positions = [i for i, value in enumerate(matched.tolist()) if bool(value)]
        if highlight_match_row:
            for pos in positions:
                styles.iloc[pos, :] = "background-color:#dbeafe;color:#1e3a8a;font-weight:900;border-top:1px solid #60a5fa;border-bottom:1px solid #60a5fa"
        elif symbol_column in frame.columns:
            col_idx = frame.columns.get_loc(symbol_column)
            for pos in positions:
                styles.iloc[pos, col_idx] = "background-color:#bfdbfe;color:#1e3a8a;font-weight:900;border:1px solid #60a5fa"

    for column in tuple(cell_extreme_highlights or ()):
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        valid = values.dropna()
        if valid.empty:
            continue
        if highlight_min_cells:
            for pos, value in enumerate(values):
                if pd.notna(value) and value == valid.min():
                    styles.iloc[pos, frame.columns.get_loc(column)] = "background-color:#bbf7d0;color:#14532d;font-weight:900"
        if highlight_max_cells:
            for pos, value in enumerate(values):
                if pd.notna(value) and value == valid.max():
                    styles.iloc[pos, frame.columns.get_loc(column)] = "background-color:#fecaca;color:#991b1b;font-weight:900"

    try:
        display = frame.style.apply(lambda _: styles, axis=None)
    except Exception:
        display = frame
    kwargs: dict[str, Any] = {"use_container_width": True, "hide_index": True}
    if desktop_height is not None:
        kwargs["height"] = int(desktop_height)
    if column_config:
        kwargs["column_config"] = dict(column_config)
    st.dataframe(display, **kwargs)


__all__ = ["render_field3_table"]
