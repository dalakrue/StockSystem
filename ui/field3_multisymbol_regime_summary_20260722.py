"""Aggregate Field 3 section for every loaded symbol.

This surface deliberately ignores the active display symbol.

Main features:
    - Middle / Lower aggregate regime views
    - Middle Regime RAS static ALLOW / DISALLOW
    - Strategy Decision: exactly four hourly selected symbols when four or more are loaded
    - Colored XLSX export
    - Persistent Middle Regime history
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from io import BytesIO
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd
from core.monthly_strategy_columns import STRATEGY_COLUMNS
from core.monthly_runtime import MONTHLY_METADATA

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

from core.global_symbol_context import get_global_symbol_context
from core.pullback_engine_s1_s3_upgrade import (
    STRATEGY_NAMES,
    evaluate_pullback_strategies,
    strategy_decision,
    ranked_pullback_scores,
)
# NOTE: the old monthly S1-S240 table renderer (ui.field3_table_renderer_20260918)
# is intentionally NOT imported anymore -- the Cycle 22 signals table below is
# the only signals table in the UI.
from core.regime_age_columns_20260722 import (
    CANDLE_AGE_COLUMN,
    RECENT_CHANGE_RANK_COLUMN,
    REGIME_START_AGE_RANK_COLUMN,
    REGIME_START_STANDARD_COLUMN,
    STANDARD_AGE_COLUMNS,
    enrich_evidence,
    enrich_ranking,
)


# ============================================================================
# DataFrame safety helpers
# ============================================================================

def _sanitize_index_column_collision(frame: Any) -> pd.DataFrame:
    """Return a safe copy when a DataFrame index name duplicates a column.

    Pandas raises ``ValueError: cannot insert <name>, already exists`` when
    ``reset_index()`` is called on a frame whose index is named the same as an
    existing column. Field 3 receives frames from several persisted/cached
    paths, so the index metadata is treated as presentation metadata and is
    cleared whenever it collides with a real column name.
    """
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    out = frame.copy()
    # Persisted snapshots can contain repeated labels after concatenation
    # (most commonly ``Datetime``).  Pandas treats a repeated label as a
    # DataFrame instead of a Series and later ``insert``/``reset_index`` calls
    # then fail with the misleading duplicate-column error.  Keep the latest
    # published value for each label before any renderer touches the frame.
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated(keep="last")].copy()
    index_name = out.index.name
    if index_name is not None and index_name in out.columns:
        out.index = out.index.rename(None)
    return out


def _sanitize_frame_collection(frames: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """Sanitize every persisted frame before concatenation/rendering."""
    return [_sanitize_index_column_collision(frame) for frame in frames
            if isinstance(frame, pd.DataFrame)]


# ============================================================================
# Optional Excel support
# ============================================================================

try:
    from openpyxl import Workbook
    from openpyxl.styles import (
        Alignment,
        Font,
        PatternFill,
    )
    from openpyxl.utils import get_column_letter
except Exception:
    Workbook = None
    Alignment = None
    Font = None
    PatternFill = None
    get_column_letter = None


# ============================================================================
# Constants
# ============================================================================

AGE_ONLY_RANK_COLUMN = "Regime Age Rank"

# Higher Standard is published separately from the Middle table, but both
# tables use the same canonical ranking snapshot.  Keep the legacy
# ``Regime Age Rank`` alias for older consumers while exposing an explicit
# higher-standard rank/age pair for the new Open/Close sections.
HIGHER_AGE_RANK_COLUMN = "Higher Regime Age Rank"
HIGHER_AGE_DISPLAY_COLUMN = "Higher Candle After Regime Start"

FIELD3_CANONICAL_TABLES_KEY = "field3_canonical_regime_tables_20260823"

MIDDLE_AGE_RANK_COLUMN = "Avg Regime Candle Rank"

# Exact hybrid execution filter requested for the Middle Standard ranking.
# The names intentionally match the supplied pandas reference implementation
# so that CSV/XLSX exports can be consumed by the same backtest/live adapter.
RISK_SCORE_COLUMN = "Risk_Score"
IS_POTENTIAL_BLOCK_COLUMN = "Is_Potential_Block"
HOURLY_BLOCK_COUNT_COLUMN = "Hourly_Block_Count"
FINAL_ACTION_COLUMN = "Final_Action"
RISK_SCORE_THRESHOLD = 1.0
HOURLY_BLOCK_QUOTA = 4
# Maximum weighted-risk SL exits per hour. Remaining exits are ranked by highest risk first.
HOURLY_SL_EXIT_QUOTA = 6

# Weighted regime-age guard.  This replaces the previous historical-loss rank
# with the user-supplied causal score:
#
#     ln(MS**1.5 * CC + 1) / ln(SA + 1)
#
# where MS is Regime Maturity Score, CC is the average completed-regime
# candle-count basis, and SA is the current Middle Standard candle age.
WEIGHTED_RISK_SCORE_COLUMN = "Weighted_Risk_Score"
WEIGHTED_RISK_DECISION_COLUMN = "Weighted Risk Decision"
WEIGHTED_RISK_THRESHOLD = 1.545

# Stop-loss permission derived from the current Middle Standard age (SA).
SL_DECISION_COLUMN = "SL"

MIDDLE_AGE_DISPLAY_COLUMN = (
    "Middle Candle After Regime Start"
)

# Price at the first candle of the current Middle Standard regime.
STARTING_PRICE_COLUMN = "Starting Price"

MIDDLE_AVG_SOURCE_COLUMN = (
    "Middle Avg Regime Candle Count Before Regime Change"
)

AVG_REGIME_CANDLE_COLUMN = (
    "Avg Regime Candle Count Before Regime Change"
)

CANDLE_STATISTICS_COLUMN = (
    "Regime Maturity Score"
)

MIDDLE_COMPLETED_SAMPLE_COLUMN = (
    "Middle Completed Regime Sample Count"
)

COMPLETED_SAMPLE_DISPLAY_COLUMN = (
    "Completed Regime Samples"
)

# --------------------------------------------------------------------------
# RAS
# --------------------------------------------------------------------------

RAS_DECISION_COLUMN = "RAS Decision"

# RAS now intentionally displays only:
#       ALLOW
#       DISALLOW
#
# The score and BUY/SELL explanation are NOT shown in the table.

# --------------------------------------------------------------------------
# Strategy Decision
# --------------------------------------------------------------------------

STRATEGY_DECISION_COLUMN = (
    "Strategy Decision"
)

# Every strategy has its own auditable condition, signal and reason.  Legacy
# Static/Statistical/Volatility/Exhaustion columns are intentionally absent.
STRATEGY_AUDIT_COLUMNS = {
    label: {
        "condition": f"{label} Entry Condition",
        "signal": f"{label} Signal",
        "reason": f"{label} Reason",
    }
    for label in STRATEGY_NAMES
}
STRATEGY_SCORE_COLUMNS = {label: f"{label} Score" for label in STRATEGY_NAMES}
STRATEGY_EXPORT_COLUMNS = tuple(
    col for label in STRATEGY_NAMES for col in STRATEGY_AUDIT_COLUMNS[label].values()
)
STATIC_PULLBACK_COLUMNS = {}
AUDIT_OHLC_COLUMNS = ("Open Price", "Close Price", "Highest Price", "Lowest Price")
REMOVED_MIDDLE_COLUMNS = (
    SL_DECISION_COLUMN, WEIGHTED_RISK_DECISION_COLUMN, WEIGHTED_RISK_SCORE_COLUMN,
    RISK_SCORE_COLUMN, IS_POTENTIAL_BLOCK_COLUMN, HOURLY_BLOCK_COUNT_COLUMN, FINAL_ACTION_COLUMN,
    "Starting Price", "Starting Process", "Middle Standard Regime State",
    "Lower Standard Regime State", "Higher Standard Regime State",
    "Posterior Probability", "Persistence Probability", "Expected Duration",
    "Changepoint Probability", "Transition Rank Probability", "Calibrated Probability",
    "Calibrated Reliability", "Data Quality Grade",
)

STRATEGY_EXPORT_COLUMNS = list(STRATEGY_COLUMNS)

def _ensure_required_audit_columns(frame):
    from core.strategy_audit_20260924 import recompute_family_evidence
    if not isinstance(frame,pd.DataFrame):return pd.DataFrame()
    out=_sanitize_index_column_collision(frame)
    for target,names in {"Open Price":("open","Open"),"Close Price":("close","Close"),"Highest Price":("high","High"),"Lowest Price":("low","Low")}.items():
        if target not in out:
            source=next((x for x in names if x in out),None)
            out[target]=pd.to_numeric(out[source],errors="coerce") if source else np.nan
    out=recompute_family_evidence(out)
    if "Strategy Decision" not in out:out["Strategy Decision"]="None"
    return out

def _load_saved_if_needed(
    state: MutableMapping[str, Any],
) -> None:

    ranking = state.get(
        "field3_multisymbol_regime_20260708"
    )

    evidence = state.get(
        "field3_regime_evidence_v2"
    )

    if (
        isinstance(ranking, pd.DataFrame)
        and not ranking.empty
        and isinstance(evidence, pd.DataFrame)
        and not evidence.empty
    ):
        return

    try:

        from core.field3_three_regime_engine import (
            load_saved_field3_v2,
        )

        load_saved_field3_v2(state)

    except Exception as exc:

        state[
            "field3_summary_reload_error_20260722"
        ] = (
            f"{type(exc).__name__}: {exc}"
        )


def _scope_to_loaded(
    frame: pd.DataFrame,
    loaded: list[str],
) -> pd.DataFrame:

    if (
        not isinstance(
            frame,
            pd.DataFrame,
        )
        or frame.empty
        or "Symbol" not in frame.columns
        or not loaded
    ):
        return frame.copy()

    allowed = {
        str(symbol).upper()
        for symbol in loaded
    }

    return frame.loc[
        frame["Symbol"]
        .astype(str)
        .str.upper()
        .isin(allowed)
    ].copy()


def _fill_middle_starting_prices_from_loaded_candles(
    ranking: pd.DataFrame,
    state: MutableMapping[str, Any],
) -> pd.DataFrame:
    """Backfill Starting Price for older saved rankings when candles exist.

    New calculation generations persist the value directly. This fallback
    keeps an older saved ranking useful by reading the already-loaded exact
    symbol candles, without fetching data or changing any calculation.
    """
    if not isinstance(ranking, pd.DataFrame) or ranking.empty or "Symbol" not in ranking.columns:
        return ranking.copy() if isinstance(ranking, pd.DataFrame) else pd.DataFrame()
    out = ranking.copy()
    if STARTING_PRICE_COLUMN not in out.columns:
        out[STARTING_PRICE_COLUMN] = pd.Series(pd.NA, index=out.index, dtype="Float64")
    prices = pd.to_numeric(out[STARTING_PRICE_COLUMN], errors="coerce")
    if prices.notna().all():
        out[STARTING_PRICE_COLUMN] = prices.round(5)
        return out
    frames = state.get("canonical_symbol_candles") if isinstance(state, Mapping) else None
    if not isinstance(frames, Mapping):
        out[STARTING_PRICE_COLUMN] = prices.round(5)
        return out
    age_col = _first_existing_column(
        out,
        ("Middle Candle After Regime Start", "Middle Regime Age", "Regime Age"),
    )
    if age_col is None:
        out[STARTING_PRICE_COLUMN] = prices.round(5)
        return out
    evaluated: dict[Any, dict[str, dict[str, Any]]] = {}
    for idx, row in out.iterrows():
        if pd.notna(prices.loc[idx]):
            continue
        symbol = str(row.get("Symbol") or "").strip().upper()
        frame = frames.get(symbol)
        if not isinstance(frame, pd.DataFrame):
            frame = frames.get(symbol.replace("/", ""))
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        age = pd.to_numeric(pd.Series([row.get(age_col)]), errors="coerce").iloc[0]
        if pd.isna(age) or float(age) < 1:
            continue
        source = next((c for c in ("open", "Open", "close", "Close") if c in frame.columns), None)
        if source is None:
            continue
        try:
            position = max(0, len(frame) - int(round(float(age))))
            value = float(pd.to_numeric(frame[source], errors="coerce").iloc[position])
            if np.isfinite(value):
                prices.loc[idx] = value
        except Exception:
            continue
    out[STARTING_PRICE_COLUMN] = prices.round(5)
    return out


def _first_existing_column(
    frame: pd.DataFrame,
    candidates: tuple[str, ...],
) -> str | None:

    if not isinstance(
        frame,
        pd.DataFrame,
    ):
        return None

    for column in candidates:
        if column in frame.columns:
            return column

    normalized = {
        str(column)
        .strip()
        .upper(): column
        for column in frame.columns
    }

    for candidate in candidates:

        found = normalized.get(
            str(candidate)
            .strip()
            .upper()
        )

        if found is not None:
            return found

    return None


# ============================================================================
# Bias normalization
# ============================================================================

def _normalize_bias(
    value: Any,
) -> str:

    if value is None:
        return "NEUTRAL"

    try:
        if pd.isna(value):
            return "NEUTRAL"
    except Exception:
        pass

    normalized = (
        str(value)
        .strip()
        .upper()
    )

    if normalized in {
        "BUY",
        "SELL",
        "NEUTRAL",
    }:
        return normalized

    if normalized in {
        "BULLISH",
        "LONG",
        "UP",
        "STRONG BUY",
    }:
        return "BUY"

    if normalized in {
        "BEARISH",
        "SHORT",
        "DOWN",
        "STRONG SELL",
    }:
        return "SELL"

    return "NEUTRAL"


# ============================================================================
# RAS calculation
# ============================================================================

def _ras_score_for_direction(
    hrb: str,
    mrb: str,
    lrb: str,
    direction: str,
) -> int:

    score = 0

    # Higher regime weight = 2
    if hrb == direction:
        score += 2
    elif hrb in {
        "BUY",
        "SELL",
    }:
        score -= 2

    # Middle regime weight = 1
    if mrb == direction:
        score += 1
    elif mrb in {
        "BUY",
        "SELL",
    }:
        score -= 1

    # Lower regime weight = 1
    if lrb == direction:
        score += 1
    elif lrb in {
        "BUY",
        "SELL",
    }:
        score -= 1

    return score


def get_ras_status(
    row: pd.Series,
) -> str:
    """
    Return ONLY:

        ALLOW
        DISALLOW

    A direction is valid when:
        score >= 1
        AND Higher Regime Bias does not oppose it.
    """

    lrb = _normalize_bias(
        row.get(
            "Lower Regime Bias"
        )
    )

    mrb = _normalize_bias(
        row.get(
            "Middle Regime Bias"
        )
    )

    hrb = _normalize_bias(
        row.get(
            "Higher Standard Regime Bias"
        )
    )

    buy_score = _ras_score_for_direction(
        hrb=hrb,
        mrb=mrb,
        lrb=lrb,
        direction="BUY",
    )

    sell_score = _ras_score_for_direction(
        hrb=hrb,
        mrb=mrb,
        lrb=lrb,
        direction="SELL",
    )

    buy_valid = (
        buy_score >= 1
        and hrb != "SELL"
    )

    sell_valid = (
        sell_score >= 1
        and hrb != "BUY"
    )

    if buy_valid or sell_valid:
        return "ALLOW"

    return "DISALLOW"


def _add_ras_decision_column(
    frame: pd.DataFrame,
) -> pd.DataFrame:

    if not isinstance(
        frame,
        pd.DataFrame,
    ):
        return pd.DataFrame()

    result = frame.copy()

    if result.empty:

        result[
            RAS_DECISION_COLUMN
        ] = pd.Series(
            dtype="object"
        )

        return result

    required_columns = {
        "Lower Regime Bias",
        "Middle Regime Bias",
        "Higher Standard Regime Bias",
    }

    if not required_columns.issubset(
        set(result.columns)
    ):

        result[
            RAS_DECISION_COLUMN
        ] = "DISALLOW"

        return result

    result[
        RAS_DECISION_COLUMN
    ] = result.apply(
        get_ras_status,
        axis=1,
    )

    return result


# ============================================================================
# Strategy Decision
# ============================================================================

def _resolve_strategy_source_columns(
    frame: pd.DataFrame,
) -> dict[str, str | None]:

    return {
        "START_AGE": _first_existing_column(
            frame,
            (
                CANDLE_AGE_COLUMN,
                "Starting Age",
                "Regime Age",
                "Candle After Regime Start",
            ),
        ),
        "LRB": _first_existing_column(
            frame,
            (
                "Lower Regime Bias",
                "LRB",
                "Lower Bias",
            ),
        ),
        "MRB": _first_existing_column(
            frame,
            (
                "Middle Regime Bias",
                "MRB",
                "Middle Bias",
            ),
        ),
        "HRB": _first_existing_column(
            frame,
            (
                "Higher Standard Regime Bias",
                "Higher Regime Bias",
                "HRB",
                "Higher Bias",
            ),
        ),
    }


def _numeric_row_value(
    row: pd.Series,
    column: str | None,
) -> float | None:

    if column is None:
        return None

    value = pd.to_numeric(
        row.get(column),
        errors="coerce",
    )

    if pd.isna(value):
        return None

    return float(value)


def _row_bias(
    row: pd.Series,
    column: str | None,
) -> str:

    if column is None:
        return "NEUTRAL"

    return _normalize_bias(
        row.get(column)
    )


def _add_historical_pullback_scores(frame):
    return _ensure_required_audit_columns(frame)

def _add_strategy_decision_column(frame):
    return _ensure_required_audit_columns(frame)

def _attach_live_pullback_data(frame,state=None):
    from core.finder_history_store_20260924 import collect_loaded_frames
    from core.monthly_runtime import live_table,latest_check,ENGINE_VERSION
    if frame.empty or state is None:return _ensure_required_audit_columns(frame)
    tf=str(state.get("timeframe") or "H1")
    out=_sanitize_index_column_collision(frame)
    if tf.upper() not in ("H1","1H"):
        return _ensure_required_audit_columns(out)
    frames,_=collect_loaded_frames(state,tf)
    check=state.get("monthly_check_time") or latest_check()
    calculated=live_table(frames,check,quotes=state.get("monthly_executable_quotes"),strict_only=state.get("monthly_strict_only",False))
    keep=[c for c in out if c=="Symbol" or c not in calculated]
    out=out[keep].merge(calculated,on="Symbol",how="left",validate="one_to_one")
    if hasattr(state,"__setitem__"):
        state["monthly_live_signals"]=calculated
        state["field3_live_audit_cache_20260924"]={"engine":ENGINE_VERSION,"check":str(check)}
    return _ensure_required_audit_columns(out)

def _first_numeric_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    """Return the first present column that contains at least one number."""
    if not isinstance(frame, pd.DataFrame):
        return None
    for name in names:
        if name not in frame.columns:
            continue
        values = pd.to_numeric(frame[name], errors="coerce")
        if values.notna().any():
            return name
    return None


def get_strategy_decision(row):
    from core.monthly_runtime import decision_text
    return decision_text(row.get("Direction"),row.get("Active S Column",""),row.get("Equation ID",""),row.get("TP Price"),row.get("SL Price")) if int(row.get("Strategy Hit Count",0) or 0)==1 else "None"

def _add_weighted_risk_score(
    table: pd.DataFrame,
    state: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Add the supplied MS/CC/SA weighted risk score and decision.

    Formula::

        Weighted_Risk_Score = ln(MS**1.5 * CC + 1) / ln(SA + 1)

    A score at or above ``1.545`` is a ``BLOCK``.  Missing/invalid inputs are
    deliberately treated as ``ALLOW`` so an incomplete snapshot is never
    silently converted into a hard trading veto.  The score is still exposed
    as ``NaN`` in that case for transparent diagnostics.
    """
    if not isinstance(table, pd.DataFrame):
        return pd.DataFrame()

    result = table.copy()
    if result.empty:
        result[WEIGHTED_RISK_SCORE_COLUMN] = pd.Series(dtype="Float64")
        result[WEIGHTED_RISK_DECISION_COLUMN] = pd.Series(dtype="object")
        result[SL_DECISION_COLUMN] = pd.Series(dtype="object")
        return _add_hourly_capped_risk_filter(result, state)

    # MS = Regime Maturity Score; CC = completed-regime candle-count basis;
    # SA = current Middle Standard candle age.  Accept legacy aliases so old
    # saved generations gain the new column without a recalculation.
    ms_column = _first_numeric_column(
        result,
        (
            CANDLE_STATISTICS_COLUMN,
            "MS (Regime Maturity Score)",
            "MS",
            "Middle Regime Maturity Score",
        ),
    )
    cc_column = _first_numeric_column(
        result,
        (
            AVG_REGIME_CANDLE_COLUMN,
            MIDDLE_AVG_SOURCE_COLUMN,
            "Candle Count Before Regime Change",
            "CC (Candle Count Before Regime Change)",
            "CC",
        ),
    )
    sa_column = _first_numeric_column(
        result,
        (
            CANDLE_AGE_COLUMN,
            "Starting Age",
            "SA (Starting Age)",
            "SA",
        ),
    )

    ms = pd.to_numeric(result[ms_column], errors="coerce") if ms_column else pd.Series(np.nan, index=result.index)
    cc = pd.to_numeric(result[cc_column], errors="coerce") if cc_column else pd.Series(np.nan, index=result.index)
    sa = pd.to_numeric(result[sa_column], errors="coerce") if sa_column else pd.Series(np.nan, index=result.index)
    valid = ms.ge(0) & cc.ge(0) & sa.gt(0)
    numerator = np.log(np.maximum(ms.clip(lower=0).to_numpy(dtype=float) ** 1.5 * cc.clip(lower=0).to_numpy(dtype=float) + 1.0, 1.0))
    denominator = np.log(sa.clip(lower=0).to_numpy(dtype=float) + 1.0)
    valid_array = valid.fillna(False).to_numpy(dtype=bool)
    score_values = np.full(len(result), np.nan, dtype=float)
    safe_denominator = valid_array & np.isfinite(denominator) & (denominator > 0)
    np.divide(numerator, denominator, out=score_values, where=safe_denominator)
    score = pd.Series(score_values, index=result.index, dtype="Float64")
    result[WEIGHTED_RISK_SCORE_COLUMN] = score.round(4)
    result[WEIGHTED_RISK_DECISION_COLUMN] = np.where(score.ge(WEIGHTED_RISK_THRESHOLD).fillna(False), "BLOCK", "ALLOW")

    # Keep the existing SL display.  The legacy weighted score remains a
    # diagnostic column, while the exact capped MS/CC/SA rule below is the
    # authoritative execution gate for this table.
    result[SL_DECISION_COLUMN] = np.where(sa < 15, "No SL", "Allowed")
    result = _add_ras_decision_column(result)
    result = _add_hourly_capped_risk_filter(result, state)
    # Apply the four-per-hour priority cap to the public decision column too.
    # Final_Action is retained as a diagnostic/execution alias, but rows that
    # lose the quota must not continue to display BLOCK in Weighted Risk Decision.
    if FINAL_ACTION_COLUMN in result.columns:
        result[WEIGHTED_RISK_DECISION_COLUMN] = np.where(
            result[FINAL_ACTION_COLUMN].astype(str).eq("BLOCK"), "BLOCK", "ALLOW"
        )
    result.loc[result[FINAL_ACTION_COLUMN].eq("BLOCK"), RAS_DECISION_COLUMN] = "DISALLOW"

    # Exit protection: block decisions and a direction flip from the previous
    # hourly snapshot of the same symbol invalidate the current trade bias.
    if isinstance(state, Mapping):
        history = state.get(MIDDLE_HISTORY_STATE_KEY)
        if isinstance(history, pd.DataFrame) and not history.empty and "Symbol" in result.columns:
            hist = history.copy()
            if "Datetime" in hist.columns:
                hist["Datetime"] = pd.to_datetime(hist["Datetime"], errors="coerce")
            if STRATEGY_DECISION_COLUMN in hist.columns:
                for idx, row in result.iterrows():
                    current_symbol = row.get("Symbol")
                    previous = hist[hist["Symbol"].eq(current_symbol)]
                    if "Datetime" in previous.columns and "Datetime" in result.columns:
                        previous = previous[previous["Datetime"] < pd.to_datetime(row.get("Datetime"), errors="coerce")]
                    if not previous.empty:
                        old_bias = str(previous.iloc[-1].get(STRATEGY_DECISION_COLUMN, "")).split("—")[0].strip()
                        new_bias = str(row.get(STRATEGY_DECISION_COLUMN, "")).split("—")[0].strip()
                        if old_bias in {"BUY", "SELL"} and new_bias in {"BUY", "SELL"} and old_bias != new_bias:
                            result.at[idx, SL_DECISION_COLUMN] = "Exit (Bias Change)"
    result.loc[result[WEIGHTED_RISK_DECISION_COLUMN].eq("BLOCK"), SL_DECISION_COLUMN] = "Exit (Risk Block)"
    result[STRATEGY_DECISION_COLUMN] = result.apply(get_strategy_decision, axis=1)
    result = _apply_hourly_sl_exit_cap(result)
    retired_columns = [
        column for column in result.columns
        if str(column).strip().lower() in {"historical_loss_pattern_risk_rank", "historicalriskrank"}
    ]
    return result.drop(
        columns=retired_columns + ["_HistoricalRiskScore", "_HistoricalRiskHour", "HistoricalRiskHour"],
        errors="ignore",
    )



def _apply_hourly_sl_exit_cap(table: pd.DataFrame) -> pd.DataFrame:
    """Limit SL exits to six per hour and prioritize highest Weighted_Risk_Score."""
    if not isinstance(table, pd.DataFrame) or table.empty or SL_DECISION_COLUMN not in table.columns:
        return table
    result = table.copy()
    dt_col = _find_datetime_column(result)
    if dt_col:
        hours = _normalize_datetime_series(result[dt_col]).dt.floor("h")
    else:
        hours = pd.Series("CURRENT_HOUR", index=result.index)
    result["_SL_Hour"] = hours.astype("object").where(hours.notna(), "CURRENT_HOUR")
    exit_mask = result[SL_DECISION_COLUMN].astype(str).str.contains("Exit", case=False, na=False)
    if WEIGHTED_RISK_SCORE_COLUMN in result.columns:
        priority = pd.to_numeric(result[WEIGHTED_RISK_SCORE_COLUMN], errors="coerce").fillna(-1)
    else:
        priority = pd.Series(-1, index=result.index)
    result["_SL_Priority"] = priority
    keep = pd.Series(False, index=result.index)
    for _, group in result[exit_mask].groupby("_SL_Hour", dropna=False):
        chosen = group.sort_values("_SL_Priority", ascending=False, kind="mergesort").head(HOURLY_SL_EXIT_QUOTA)
        keep.loc[chosen.index] = True
    result.loc[exit_mask & ~keep, SL_DECISION_COLUMN] = "Hold (SL Exit Hourly Cap)"
    return result.drop(columns=["_SL_Hour", "_SL_Priority"], errors="ignore")


def _add_hourly_capped_risk_filter(
    table: pd.DataFrame,
    state: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Apply the exact ``MS * CC / SA`` rule with a four-block hourly cap.

    A potential block is counted only when it is actually blocked.  Once four
    blocks have been issued in a calendar hour, later potential blocks in that
    hour are allowed, exactly as the requested execution rule specifies.  The
    calculation is deterministic for a historical table: rows are evaluated
    chronologically (with the incoming row order as a stable tie-breaker) and
    then returned in their original order.
    """
    del state  # reserved for a live adapter; historical tables are self-contained
    if not isinstance(table, pd.DataFrame):
        return pd.DataFrame()

    result = table.copy()
    if result.empty:
        result[RISK_SCORE_COLUMN] = pd.Series(dtype="Float64")
        result[IS_POTENTIAL_BLOCK_COLUMN] = pd.Series(dtype="boolean")
        result[HOURLY_BLOCK_COUNT_COLUMN] = pd.Series(dtype="Int64")
        result[FINAL_ACTION_COLUMN] = pd.Series(dtype="object")
        return result

    ms_column = _first_numeric_column(
        result,
        (
            CANDLE_STATISTICS_COLUMN,
            "MS (Regime Maturity Score)",
            "MS",
            "Middle Regime Maturity Score",
        ),
    )
    cc_column = _first_numeric_column(
        result,
        (
            AVG_REGIME_CANDLE_COLUMN,
            MIDDLE_AVG_SOURCE_COLUMN,
            "Candle Count Before Regime Change",
            "CC (Candle Count Before Regime Change)",
            "CC",
        ),
    )
    sa_column = _first_numeric_column(
        result,
        (
            CANDLE_AGE_COLUMN,
            "Starting Age",
            "SA (Starting Age)",
            "SA",
        ),
    )

    ms = (
        pd.to_numeric(result[ms_column], errors="coerce")
        if ms_column
        else pd.Series(np.nan, index=result.index)
    )
    cc = (
        pd.to_numeric(result[cc_column], errors="coerce")
        if cc_column
        else pd.Series(np.nan, index=result.index)
    )
    sa = (
        pd.to_numeric(result[sa_column], errors="coerce")
        if sa_column
        else pd.Series(np.nan, index=result.index)
    )

    valid = ms.ge(0) & cc.ge(0) & sa.gt(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = (ms * cc).div(sa)
    scores = scores.where(valid & np.isfinite(scores), np.nan)
    result[RISK_SCORE_COLUMN] = scores.round(6).astype("Float64")
    potential = result[RISK_SCORE_COLUMN].ge(RISK_SCORE_THRESHOLD).fillna(False).astype(bool)
    result[IS_POTENTIAL_BLOCK_COLUMN] = potential.astype("boolean")

    # ``Completed Candle`` is the standard table's timestamp.  Support the
    # broader aliases used by historical exports and live adapters as well.
    datetime_column = _find_datetime_column(result)
    if datetime_column is not None:
        timestamps = _normalize_datetime_series(result[datetime_column])
    else:
        timestamps = pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns]")

    # A current ranking can legitimately omit a timestamp.  Treat all such
    # rows as one current-hour bucket instead of silently resetting the quota
    # for every symbol.
    hour_values = timestamps.dt.floor("h")
    hour_values = hour_values.astype("object").where(hour_values.notna(), "CURRENT_HOUR")
    result["Hour"] = hour_values

    working = pd.DataFrame(
        {
            "__original_order": np.arange(len(result), dtype=int),
            "__timestamp": timestamps,
            "__hour": hour_values,
            "__potential": potential.to_numpy(dtype=bool),
        },
        index=result.index,
    )
    working = working.sort_values(
        ["__timestamp", "__original_order"],
        na_position="last",
        kind="mergesort",
    )

    # Priority rule: when more than four symbols qualify in the same hour,
    # keep only the four largest Risk_Score values. This prevents row order
    # from deciding which symbols receive protection.
    working["__risk_score"] = result[RISK_SCORE_COLUMN].reindex(working.index)
    working["__selected"] = False
    for hour_key, group in working.groupby("__hour", dropna=False):
        candidates = group[group["__potential"]].sort_values(
            ["__risk_score", "__original_order"],
            ascending=[False, True],
            kind="mergesort",
        )
        working.loc[candidates.head(HOURLY_BLOCK_QUOTA).index, "__selected"] = True

    counts: dict[Any, int] = {}
    actions: dict[Any, str] = {}
    for row_index, row in working.iterrows():
        hour_key = row["__hour"]
        if bool(row["__selected"]):
            actions[row_index] = "BLOCK"
        else:
            actions[row_index] = "ALLOW"
        counts[row_index] = int(working.loc[(working["__hour"] == hour_key) & working["__selected"]].shape[0])

    result[HOURLY_BLOCK_COUNT_COLUMN] = pd.Series(
        [counts.get(index, 0) for index in result.index],
        index=result.index,
        dtype="Int64",
    )
    result[FINAL_ACTION_COLUMN] = pd.Series(
        [actions.get(index, "ALLOW") for index in result.index],
        index=result.index,
        dtype="object",
    )
    return result
# ============================================================================
# Standard table
# ============================================================================

def _standard_table(
    evidence: pd.DataFrame,
    ranking: pd.DataFrame,
    standard: str,
) -> pd.DataFrame:

    standard_series = evidence.get(
        "Standard",
        pd.Series(
            "",
            index=evidence.index,
        ),
    )

    scoped = evidence.loc[
        standard_series
        .astype(str)
        .str.upper()
        .eq(
            standard
        )
    ].copy()

    if scoped.empty:
        return scoped

    current_rank = ranking[
        [
            c
            for c in (
                "Symbol",
                "Rank",
            )
            if c in ranking.columns
        ]
    ].copy()

    if set(
        current_rank.columns
    ) == {
        "Symbol",
        "Rank",
    }:

        scoped = scoped.merge(
            current_rank.rename(
                columns={
                    "Rank": "Final Rank"
                }
            ),
            on="Symbol",
            how="left",
        )

    if CANDLE_AGE_COLUMN in scoped.columns:

        age = pd.to_numeric(
            scoped[
                CANDLE_AGE_COLUMN
            ],
            errors="coerce",
        )

        scoped[
            REGIME_START_AGE_RANK_COLUMN
        ] = (
            age.rank(
                method="min",
                ascending=False,
                na_option="bottom",
            )
            .astype("Int64")
        )

        scoped[
            RECENT_CHANGE_RANK_COLUMN
        ] = (
            age.rank(
                method="min",
                ascending=True,
                na_option="bottom",
            )
            .astype("Int64")
        )

    columns = [
        REGIME_START_AGE_RANK_COLUMN,
        RECENT_CHANGE_RANK_COLUMN,
        "Final Rank",
        "Symbol",
        "Regime State",
        "Bias",
        "Posterior Probability",
        "Persistence Probability",
        "Expected Duration",
        CANDLE_AGE_COLUMN,
        "Changepoint Probability",
        "Transition Risk",
        "Sample Count",
        "Data Quality Grade",
        "Completed Candle",
    ]

    table = scoped[
        [
            c
            for c in columns
            if c in scoped.columns
        ]
    ].copy()

    sort_cols = [
        c
        for c in (
            RECENT_CHANGE_RANK_COLUMN,
            "Final Rank",
            "Symbol",
        )
        if c in table.columns
    ]

    if sort_cols:

        return (
            table
            .sort_values(
                sort_cols,
                kind="mergesort",
            )
            .reset_index(
                drop=True
            )
        )

    return table.reset_index(
        drop=True
    )


# ============================================================================
# Higher regime ranking
# ============================================================================

def _age_only_ranking(
    ranking: pd.DataFrame,
) -> pd.DataFrame:
    """Build the Higher Standard ranking from the same snapshot as Middle.

    This used to be a dead compatibility helper: it calculated a frame but
    the main renderer never called it, so opening/closing the higher section
    could not show anything.  The function now keeps a dedicated higher age
    column/rank and adds the same RAS/Strategy columns used by Middle.  No
    calculation or provider call is performed here; ``ranking`` is already
    the enriched, saved Field 3 snapshot.
    """

    if not isinstance(ranking, pd.DataFrame) or ranking.empty:
        return pd.DataFrame()

    higher_age_column = STANDARD_AGE_COLUMNS["HIGHER"]
    source_age = (
        higher_age_column
        if higher_age_column in ranking.columns
        else CANDLE_AGE_COLUMN
        if CANDLE_AGE_COLUMN in ranking.columns
        else None
    )
    if "Symbol" not in ranking.columns or source_age is None:
        return pd.DataFrame()

    source_columns = [
        "Symbol",
        source_age,
        REGIME_START_STANDARD_COLUMN,
        "Lower Regime",
        "Lower Bias",
        "Middle Regime",
        "Middle Bias",
        "Higher Regime",
        "Higher Bias",
        "Completed Candle",
        "Timeframe",
    ]
    table = ranking[[column for column in source_columns if column in ranking.columns]].copy()
    table = table.rename(columns={source_age: HIGHER_AGE_DISPLAY_COLUMN})
    table[HIGHER_AGE_DISPLAY_COLUMN] = pd.to_numeric(
        table[HIGHER_AGE_DISPLAY_COLUMN], errors="coerce"
    )
    table = (
        table.dropna(subset=[HIGHER_AGE_DISPLAY_COLUMN])
        .drop_duplicates(subset=["Symbol"], keep="first")
    )
    if table.empty:
        return table

    table[HIGHER_AGE_RANK_COLUMN] = (
        table[HIGHER_AGE_DISPLAY_COLUMN]
        .rank(method="min", ascending=True, na_option="bottom")
        .astype("Int64")
    )
    # The shared strategy resolver reads the canonical age alias.  Point it at
    # Higher's age for this table without changing the Middle table's value.
    table[CANDLE_AGE_COLUMN] = table[HIGHER_AGE_DISPLAY_COLUMN]
    # Preserve the old key for external exports that still expect it.
    table[AGE_ONLY_RANK_COLUMN] = table[HIGHER_AGE_RANK_COLUMN]

    table = table.rename(
        columns={
            "Higher Regime": "Higher Standard Regime State",
            "Higher Bias": "Higher Standard Regime Bias",
            "Middle Regime": "Middle Standard Regime State",
            "Middle Bias": "Middle Regime Bias",
            "Lower Regime": "Lower Standard Regime State",
            "Lower Bias": "Lower Regime Bias",
        }
    )
    # Use the canonical RAS/strategy rules so Higher's Open and Close views do
    # not silently disagree with the Middle table.
    table = _add_strategy_decision_column(table)

    ordered = [
        HIGHER_AGE_RANK_COLUMN,
        SL_DECISION_COLUMN,
        "Symbol",
        *MONTHLY_METADATA,
        *STRATEGY_EXPORT_COLUMNS,
        *STRATEGY_SCORE_COLUMNS.values(),
        STRATEGY_DECISION_COLUMN,
        WEIGHTED_RISK_DECISION_COLUMN,
        "Lower Regime Bias",
        "Middle Regime Bias",
        "Higher Standard Regime Bias",
        HIGHER_AGE_DISPLAY_COLUMN,
        RAS_DECISION_COLUMN,
        "Higher Standard Regime State",
        "Middle Standard Regime State",
        "Lower Standard Regime State",
        REGIME_START_STANDARD_COLUMN,
        "Completed Candle",
        "Timeframe",
        AGE_ONLY_RANK_COLUMN,
    ]
    table = table[[column for column in ordered if column in table.columns]]
    return table.sort_values(
        [HIGHER_AGE_RANK_COLUMN, "Symbol"], kind="mergesort"
    ).reset_index(drop=True)


def _publish_higher_ranking_to_field_sections(
    state: MutableMapping[str, Any],
    higher_ranking: pd.DataFrame,
) -> None:
    """
    Publish Higher Standard Regime ranking to both Field Close and
    Field Open state locations.

    Field Close is explicitly designated as the first section.

    The actual Field Open / Field Close renderer in your application
    can consume these state objects without recomputing the ranking.
    """

    if not isinstance(
        higher_ranking,
        pd.DataFrame,
    ):
        higher_ranking = pd.DataFrame()

    ranking_copy = (
        higher_ranking.copy()
    )

    state[
        FIELD_CLOSE_HIGHER_RANKING_KEY
    ] = ranking_copy.copy()

    state[
        FIELD_OPEN_HIGHER_RANKING_KEY
    ] = ranking_copy.copy()

    state[
        FIELD_CLOSE_HIGHER_MOBILE_KEY
    ] = ranking_copy.copy()
    state[
        FIELD_OPEN_HIGHER_MOBILE_KEY
    ] = ranking_copy.copy()

    # Mobile cards use the same canonical dataframe.

    # Keep a single, auditable publication bundle.  Field Open/Close and the
    # standalone Field 3 renderer can therefore read the exact same Higher
    # frame instead of rebuilding a second version on demand.
    canonical = state.get(FIELD3_CANONICAL_TABLES_KEY)
    if not isinstance(canonical, MutableMapping):
        canonical = {}
    canonical["higher"] = ranking_copy.copy()
    state[FIELD3_CANONICAL_TABLES_KEY] = canonical

    # Explicit ordering.
    state[
        FIELD_SECTION_ORDER_KEY
    ] = (
        "FIELD_CLOSE",
        "FIELD_OPEN",
    )








# ============================================================================
# Middle regime ranking
# ============================================================================

def _middle_age_ranking(
    ranking: pd.DataFrame,
) -> pd.DataFrame:

    if (
        not isinstance(
            ranking,
            pd.DataFrame,
        )
        or ranking.empty
    ):
        return pd.DataFrame()

    middle_age_column = (
        STANDARD_AGE_COLUMNS[
            "MIDDLE"
        ]
    )

    columns = [
        c
        for c in (
            "Symbol",
            middle_age_column,

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

    if (
        "Symbol" not in columns
        or middle_age_column not in columns
    ):
        return pd.DataFrame()

    table = ranking[
        columns
    ].copy()

    # Normalize all calculation lanes and older saved generations to one
    # stable display column. Older rows remain visible with a blank value.
    starting_price_source = _first_existing_column(
        ranking,
        (
            STARTING_PRICE_COLUMN,
            "Middle Regime Starting Price",
            "Middle Starting Price",
            "Regime Start Price",
        ),
    )
    if starting_price_source is not None:
        table[STARTING_PRICE_COLUMN] = pd.to_numeric(
            ranking[starting_price_source],
            errors="coerce",
        ).round(5)
    else:
        table[STARTING_PRICE_COLUMN] = pd.Series(
            pd.NA,
            index=table.index,
            dtype="Float64",
        )

    # ----------------------------------------------------------------------
    # Starting age
    # ----------------------------------------------------------------------

    table[
        CANDLE_AGE_COLUMN
    ] = pd.to_numeric(
        table[
            middle_age_column
        ],
        errors="coerce",
    )

    # ----------------------------------------------------------------------
    # Average regime count
    # ----------------------------------------------------------------------

    if (
        MIDDLE_AVG_SOURCE_COLUMN
        in table.columns
    ):

        table[
            AVG_REGIME_CANDLE_COLUMN
        ] = pd.to_numeric(
            table[
                MIDDLE_AVG_SOURCE_COLUMN
            ],
            errors="coerce",
        ).round(2)

    if (
        MIDDLE_COMPLETED_SAMPLE_COLUMN
        in table.columns
    ):

        table[
            COMPLETED_SAMPLE_DISPLAY_COLUMN
        ] = pd.to_numeric(
            table[
                MIDDLE_COMPLETED_SAMPLE_COLUMN
            ],
            errors="coerce",
        ).astype("Int64")

    # ----------------------------------------------------------------------
    # Regime maturity
    # ----------------------------------------------------------------------

    if (
        AVG_REGIME_CANDLE_COLUMN
        in table.columns
        and
        COMPLETED_SAMPLE_DISPLAY_COLUMN
        in table.columns
    ):

        avg_candles = pd.to_numeric(
            table[
                AVG_REGIME_CANDLE_COLUMN
            ],
            errors="coerce",
        )

        sample_count = pd.to_numeric(
            table[
                COMPLETED_SAMPLE_DISPLAY_COLUMN
            ],
            errors="coerce",
        )

        table[
            CANDLE_STATISTICS_COLUMN
        ] = (
            table[
                CANDLE_AGE_COLUMN
            ]
            .div(
                avg_candles
            )
            .mul(
                np.log1p(
                    sample_count
                )
            )
            .where(
                (avg_candles > 0)
                & (sample_count > 0)
            )
            .round(2)
        )

    table = (
        table
        .dropna(
            subset=[
                CANDLE_AGE_COLUMN
            ]
        )
        .drop_duplicates(
            subset=[
                "Symbol"
            ],
            keep="first",
        )
    )

    if table.empty:
        return table

    # Establish the requested youngest-SA-first order before assigning a
    # strict rank; symbol is the deterministic tie-breaker for equal ages.
    table = table.sort_values(
        [CANDLE_AGE_COLUMN, "Symbol"],
        ascending=[True, True],
        kind="mergesort",
    ).reset_index(drop=True)

    table[
        MIDDLE_AGE_RANK_COLUMN
    ] = (
        table[
            CANDLE_AGE_COLUMN
        ]
        .rank(
            # A strict first-to-last priority is easier to read than tied
            # ranks: rank 1 is always the youngest SA in this snapshot.
            method="first",
            ascending=True,
        )
        .astype("Int64")
    )

    ordered = [
        MIDDLE_AGE_RANK_COLUMN,
        "Symbol",
        "Lower Bias",
        "Middle Bias",
        "Higher Bias",
        CANDLE_AGE_COLUMN,
        STARTING_PRICE_COLUMN,
        CANDLE_STATISTICS_COLUMN,
        AVG_REGIME_CANDLE_COLUMN,
        COMPLETED_SAMPLE_DISPLAY_COLUMN,
        "Middle Regime",
        "Lower Regime",
        "Higher Regime",
        "Completed Candle",
        "Timeframe",
    ]

    table = table[
        [
            c
            for c in ordered
            if c in table.columns
        ]
    ]

    table = table.rename(
        columns={
            "Middle Regime":
                "Middle Standard Regime State",
            "Middle Bias":
                "Middle Regime Bias",
            "Lower Regime":
                "Lower Standard Regime State",
            "Lower Bias":
                "Lower Regime Bias",
            "Higher Regime":
                "Higher Standard Regime State",
            "Higher Bias":
                "Higher Standard Regime Bias",
        }
    )

    # ----------------------------------------------------------------------
    # RAS
    # ----------------------------------------------------------------------

    table = _add_ras_decision_column(
        table
    )

    # ----------------------------------------------------------------------
    # Strategy Decision
    # ----------------------------------------------------------------------

    table = _add_strategy_decision_column(
        table
    )
    table = _ensure_required_audit_columns(table)

    # ----------------------------------------------------------------------
    # FINAL COLUMN ORDER
    #
    # Symbol
    # Strategy Decision
    # Lower Bias
    # Middle Bias
    # Higher Bias
    # Starting Age
    # RAS
    #
    # RAS is immediately beside Starting Age.
    # ----------------------------------------------------------------------

    preferred_order = [
        STRATEGY_DECISION_COLUMN,
        MIDDLE_AGE_RANK_COLUMN,
        "Symbol",
        "Lower Regime Bias",
        "Middle Regime Bias",
        "Higher Standard Regime Bias",
        CANDLE_AGE_COLUMN,
        STARTING_PRICE_COLUMN,
        "Hour",
        RAS_DECISION_COLUMN,
        CANDLE_STATISTICS_COLUMN,
        AVG_REGIME_CANDLE_COLUMN,
        COMPLETED_SAMPLE_DISPLAY_COLUMN,
        "Middle Standard Regime State",
        *MONTHLY_METADATA,
        *STRATEGY_EXPORT_COLUMNS,
        *STRATEGY_SCORE_COLUMNS.values(),
        *AUDIT_OHLC_COLUMNS,
        "Lower Standard Regime State",
        "Higher Standard Regime State",
        "Completed Candle",
        "Timeframe",
    ]

    table = table[[c for c in preferred_order if c in table.columns] + [c for c in table.columns if c not in preferred_order]]

    return (
        table
        .sort_values(
            [
                CANDLE_AGE_COLUMN,
                "Symbol",
            ],
            ascending=[
                True,
                True,
            ],
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================================
# Datetime helpers
# ============================================================================

def _normalize_datetime_value(
    value: Any,
) -> pd.Timestamp | None:

    if value is None:
        return None

    try:
        parsed = pd.to_datetime(
            value,
            errors="coerce",
        )
    except Exception:
        return None

    if pd.isna(parsed):
        return None

    try:
        timestamp = pd.Timestamp(
            parsed
        )
    except Exception:
        return None

    try:

        if timestamp.tz is not None:
            timestamp = (
                timestamp.tz_localize(
                    None
                )
            )

    except Exception:

        try:
            timestamp = (
                timestamp.tz_convert(
                    None
                )
            )

        except Exception:
            pass

    return timestamp


def _normalize_datetime_series(
    values: Any,
) -> pd.Series:

    try:

        parsed = pd.to_datetime(
            values,
            errors="coerce",
        )

    except Exception:

        return pd.Series(
            index=getattr(
                values,
                "index",
                None,
            ),
            dtype="datetime64[ns]",
        )

    if isinstance(
        parsed,
        pd.DatetimeIndex,
    ):

        try:

            if parsed.tz is not None:
                parsed = parsed.tz_localize(
                    None
                )

        except Exception:
            pass

    elif isinstance(
        parsed,
        pd.Series,
    ):

        try:

            if (
                getattr(
                    parsed.dt,
                    "tz",
                    None,
                )
                is not None
            ):

                parsed = (
                    parsed.dt.tz_localize(
                        None
                    )
                )

        except Exception:

            parsed = parsed.apply(
                _normalize_datetime_value
            )

    return parsed


def _find_datetime_column(
    frame: pd.DataFrame,
) -> str | None:

    if (
        not isinstance(
            frame,
            pd.DataFrame,
        )
        or frame.empty
    ):
        return None

    candidates = (
        "Datetime",
        "DateTime",
        "datetime",
        "Timestamp",
        "timestamp",
        "Snapshot Datetime",
        "Snapshot DateTime",
        "Current Candle Datetime",
        "Current Candle DateTime",
        "Current Candle Timestamp",
        "Completed Candle Datetime",
        "Completed Candle DateTime",
        "Completed Candle Time",
        "Completed Candle",
        "Candle Datetime",
        "Candle DateTime",
        "Candle Time",
        "Time",
        "time",
        "Date",
        "date",
    )

    for column in candidates:

        if column not in frame.columns:
            continue

        values = frame[
            column
        ]

        if pd.api.types.is_bool_dtype(
            values
        ):
            continue

        parsed = (
            _normalize_datetime_series(
                values
            )
        )

        if (
            isinstance(
                parsed,
                pd.Series,
            )
            and parsed.notna().any()
        ):
            return column

    for column in frame.columns:

        name = str(
            column
        ).lower()

        if (
            "datetime" in name
            or "timestamp" in name
            or "candle time" in name
            or name == "date"
            or name == "time"
        ):

            values = frame[
                column
            ]

            if pd.api.types.is_bool_dtype(
                values
            ):
                continue

            parsed = (
                _normalize_datetime_series(
                    values
                )
            )

            if (
                isinstance(
                    parsed,
                    pd.Series,
                )
                and parsed.notna().any()
            ):
                return column

    return None


def _resolve_datetime_from_frame(
    frame: pd.DataFrame,
    candidates: tuple[str, ...],
) -> pd.Timestamp | None:

    if (
        not isinstance(
            frame,
            pd.DataFrame,
        )
        or frame.empty
    ):
        return None

    for column in candidates:

        if column not in frame.columns:
            continue

        values = frame[
            column
        ]

        if pd.api.types.is_bool_dtype(
            values
        ):
            continue

        parsed = (
            _normalize_datetime_series(
                values
            )
        )

        if (
            isinstance(
                parsed,
                pd.Series,
            )
            and parsed.notna().any()
        ):

            try:

                return pd.Timestamp(
                    parsed
                    .dropna()
                    .max()
                )

            except Exception:
                continue

    return None


def _resolve_current_candle_datetime(
    ranking: pd.DataFrame,
    state: MutableMapping[str, Any],
) -> pd.Timestamp | None:

    candidates = (
        "Snapshot Datetime",
        "Snapshot DateTime",
        "Snapshot Timestamp",
        "Current Candle Datetime",
        "Current Candle DateTime",
        "Current Candle Timestamp",
        "Candle Datetime",
        "Candle DateTime",
        "Candle Time",
        "Completed Candle Datetime",
        "Completed Candle DateTime",
        "Completed Candle Time",
        "Datetime",
        "DateTime",
        "datetime",
        "Timestamp",
        "timestamp",
        "Completed Candle",
    )

    resolved = (
        _resolve_datetime_from_frame(
            ranking,
            candidates,
        )
    )

    if resolved is not None:
        return resolved

    evidence = state.get(
        "field3_regime_evidence_v2"
    )

    resolved = (
        _resolve_datetime_from_frame(
            evidence,
            candidates,
        )
    )

    if resolved is not None:
        return resolved

    state_keys = (
        "field3_current_candle_datetime",
        "field3_current_candle_datetime_20260722",
        "field3_current_candle_timestamp",
        "current_candle_datetime",
        "current_candle_time",
        "current_candle_timestamp",
        "field3_candle_datetime",
        "field3_candle_time",
        "field3_candle_timestamp",
        "completed_candle_datetime",
        "completed_candle_time",
        "completed_candle_timestamp",
        "last_candle_datetime",
        "last_candle_time",
        "last_candle_timestamp",
        "last_completed_candle_datetime",
        "last_completed_candle_time",
        "current_datetime",
        "current_timestamp",
    )

    for key in state_keys:

        parsed = (
            _normalize_datetime_value(
                state.get(key)
            )
        )

        if parsed is not None:
            return parsed

    return None


# ============================================================================
# Historical storage
# ============================================================================


def _hourly_entry_export(frame):
    # Export every raw row and all 240 columns; portfolio admission is separate.
    return frame.copy() if isinstance(frame,pd.DataFrame) else pd.DataFrame()



# ============================================================================
# Excel styling
# ============================================================================

def _style_excel_sheet(
    worksheet: Any,
    dataframe: pd.DataFrame,
) -> None:

    if (
        dataframe.empty
        or PatternFill is None
    ):
        return

    fill_header = PatternFill(
        fill_type="solid",
        fgColor="D9EAF7",
    )

    fill_min = PatternFill(
        fill_type="solid",
        fgColor="C6EFCE",
    )

    fill_max = PatternFill(
        fill_type="solid",
        fgColor="FFC7CE",
    )

    fill_match = PatternFill(
        fill_type="solid",
        fgColor="DDEBF7",
    )

    fill_top = PatternFill(
        fill_type="solid",
        fgColor="E2F0D9",
    )

    fill_bottom = PatternFill(
        fill_type="solid",
        fgColor="FCE4D6",
    )

    fill_allow = PatternFill(
        fill_type="solid",
        fgColor="C6EFCE",
    )

    fill_disallow = PatternFill(
        fill_type="solid",
        fgColor="FFC7CE",
    )

    fill_s1 = PatternFill(
        fill_type="solid",
        fgColor="FFF2CC",
    )

    fill_s2 = PatternFill(
        fill_type="solid",
        fgColor="FCE4D6",
    )

    fill_s3 = PatternFill(
        fill_type="solid",
        fgColor="E4DFEC",
    )

    fill_none = PatternFill(
        fill_type="solid",
        fgColor="F2F2F2",
    )

    for cell in worksheet[1]:

        cell.fill = fill_header

        if Font is not None:
            cell.font = Font(
                bold=True
            )

        if Alignment is not None:
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

    # ----------------------------------------------------------------------
    # Numeric extremes
    # ----------------------------------------------------------------------

    extremes: dict[
        str,
        tuple[Any, Any],
    ] = {}

    for column in (
        MIDDLE_NUMERIC_HIGHLIGHT_COLUMNS
    ):

        if column not in dataframe.columns:
            continue

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        ).dropna()

        if values.empty:
            continue

        extremes[column] = (
            values.min(),
            values.max(),
        )

    # ----------------------------------------------------------------------
    # Matching bias rows
    # ----------------------------------------------------------------------

    matching_indexes: set[Any] = set()

    if (
        "Middle Regime Bias"
        in dataframe.columns
        and
        "Higher Standard Regime Bias"
        in dataframe.columns
    ):

        middle_bias = (
            dataframe[
                "Middle Regime Bias"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        higher_bias = (
            dataframe[
                "Higher Standard Regime Bias"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        matching_indexes = set(
            dataframe.index[
                middle_bias.eq(
                    higher_bias
                )
            ]
        )

    # ----------------------------------------------------------------------
    # Top / bottom
    # ----------------------------------------------------------------------

    top_indexes: set[Any] = set()
    bottom_indexes: set[Any] = set()

    if (
        MIDDLE_AGE_RANK_COLUMN
        in dataframe.columns
    ):

        ranks = pd.to_numeric(
            dataframe[
                MIDDLE_AGE_RANK_COLUMN
            ],
            errors="coerce",
        ).dropna()

        if not ranks.empty:

            ordered = (
                ranks
                .sort_values()
                .index
                .tolist()
            )

            top_indexes = set(
                ordered[:5]
            )

            bottom_indexes = set(
                ordered[-5:]
            )

    # ----------------------------------------------------------------------
    # Rows
    # ----------------------------------------------------------------------

    for excel_row, df_index in enumerate(
        dataframe.index,
        start=2,
    ):

        if (
            df_index
            in matching_indexes
        ):
            row_fill = fill_match

        elif (
            df_index
            in top_indexes
        ):
            row_fill = fill_top

        elif (
            df_index
            in bottom_indexes
        ):
            row_fill = fill_bottom

        else:
            row_fill = None

        if row_fill is not None:

            for cell in worksheet[
                excel_row
            ]:

                cell.fill = row_fill

        # --------------------------------------------------------------
        # Numeric min/max
        # --------------------------------------------------------------

        for column, (
            minimum,
            maximum,
        ) in extremes.items():

            column_index = (
                dataframe.columns.get_loc(
                    column
                )
                + 1
            )

            value = pd.to_numeric(
                dataframe.loc[
                    df_index,
                    column,
                ],
                errors="coerce",
            )

            if pd.isna(value):
                continue

            cell = worksheet.cell(
                row=excel_row,
                column=column_index,
            )

            if (
                value == minimum
                and value == maximum
            ):
                cell.fill = fill_min

            elif value == minimum:
                cell.fill = fill_min

            elif value == maximum:
                cell.fill = fill_max

        # --------------------------------------------------------------
        # RAS
        # --------------------------------------------------------------

        if (
            RAS_DECISION_COLUMN
            in dataframe.columns
        ):

            ras_index = (
                dataframe.columns.get_loc(
                    RAS_DECISION_COLUMN
                )
                + 1
            )

            ras_cell = worksheet.cell(
                row=excel_row,
                column=ras_index,
            )

            ras_value = str(
                dataframe.loc[
                    df_index,
                    RAS_DECISION_COLUMN,
                ]
            ).upper()

            if ras_value == "ALLOW":
                ras_cell.fill = fill_allow

            else:
                ras_cell.fill = fill_disallow

        # --------------------------------------------------------------
        # Weighted risk decision
        # --------------------------------------------------------------

        if WEIGHTED_RISK_DECISION_COLUMN in dataframe.columns:
            weighted_index = dataframe.columns.get_loc(WEIGHTED_RISK_DECISION_COLUMN) + 1
            weighted_cell = worksheet.cell(row=excel_row, column=weighted_index)
            weighted_value = str(dataframe.loc[df_index, WEIGHTED_RISK_DECISION_COLUMN]).upper()
            weighted_cell.fill = fill_disallow if weighted_value == "BLOCK" else fill_allow

        if FINAL_ACTION_COLUMN in dataframe.columns:
            action_index = dataframe.columns.get_loc(FINAL_ACTION_COLUMN) + 1
            action_cell = worksheet.cell(row=excel_row, column=action_index)
            action_value = str(dataframe.loc[df_index, FINAL_ACTION_COLUMN]).upper()
            action_cell.fill = fill_disallow if action_value == "BLOCK" else fill_allow

        # --------------------------------------------------------------
        # Strategy
        # --------------------------------------------------------------

        if (
            STRATEGY_DECISION_COLUMN
            in dataframe.columns
        ):

            strategy_index = (
                dataframe.columns.get_loc(
                    STRATEGY_DECISION_COLUMN
                )
                + 1
            )

            strategy_cell = worksheet.cell(
                row=excel_row,
                column=strategy_index,
            )

            strategy = str(
                dataframe.loc[
                    df_index,
                    STRATEGY_DECISION_COLUMN,
                ]
            ).upper()

            if strategy.startswith("S1"):
                strategy_cell.fill = fill_s1

            elif strategy.startswith("S2"):
                strategy_cell.fill = fill_s2

            elif strategy.startswith("S3"):
                strategy_cell.fill = fill_s3

            elif strategy.startswith("S4"):
                strategy_cell.fill = fill_disallow

            else:
                strategy_cell.fill = fill_none

    # ----------------------------------------------------------------------
    # Width
    # ----------------------------------------------------------------------

    if (
        get_column_letter is not None
    ):

        for column_index, column_name in enumerate(
            dataframe.columns,
            start=1,
        ):

            maximum = len(
                str(column_name)
            )

            for cell in worksheet[
                get_column_letter(
                    column_index
                )
            ]:

                if cell.value is not None:

                    maximum = max(
                        maximum,
                        len(
                            str(
                                cell.value
                            )
                        ),
                    )

            worksheet.column_dimensions[
                get_column_letter(
                    column_index
                )
            ].width = min(
                max(
                    maximum + 2,
                    12,
                ),
                42,
            )

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = (
        worksheet.dimensions
    )


def _dataframe_to_excel(
    dataframe: pd.DataFrame,
    sheet_name: str,
) -> bytes | None:

    if (
        Workbook is None
        or not isinstance(
            dataframe,
            pd.DataFrame,
        )
    ):
        return None

    workbook = Workbook()

    worksheet = workbook.active

    worksheet.title = (
        sheet_name[:31]
    )

    # Header
    for column_index, column_name in enumerate(
        dataframe.columns,
        start=1,
    ):

        worksheet.cell(
            row=1,
            column=column_index,
            value=str(
                column_name
            ),
        )

    # Data.  Excel/openpyxl does not accept timezone-aware datetime objects;
    # normalize every datetime-like value to a timezone-naive Python value (or
    # a formatted string) before assigning cells.
    for row_index, (_, row) in enumerate(
        dataframe.iterrows(),
        start=2,
    ):

        for column_index, value in enumerate(
            row,
            start=1,
        ):

            if isinstance(value, (pd.Timestamp,)):
                value = _normalize_datetime_value(value)
                if value is not None:
                    value = value.to_pydatetime().replace(tzinfo=None)
            elif isinstance(value, (np.datetime64,)):
                parsed = _normalize_datetime_value(value)
                value = parsed.to_pydatetime().replace(tzinfo=None) if parsed is not None else None
            elif getattr(value, "tzinfo", None) is not None:
                value = value.replace(tzinfo=None)
            try:
                if pd.isna(value):
                    value = None
            except Exception:
                pass

            if isinstance(value, (list, tuple, dict, set)):
                value = str(value)

            worksheet.cell(
                row=row_index,
                column=column_index,
                value=value,
            )

    _style_excel_sheet(
        worksheet,
        dataframe,
    )

    output = BytesIO()

    workbook.save(
        output
    )

    output.seek(0)

    return output.getvalue()


def _canonical_middle_export_frame(
    dataframe: pd.DataFrame,
    state: Mapping[str, Any] | None = None,
    *,
    datetime_first: bool = False,
) -> pd.DataFrame:
    """Return the exact Field 3 Middle layout used by the visible table.

    Risk/SL columns are added after the ranking builder, so relying on the
    dataframe's insertion order used to append SL near the end of CSV/XLSX
    exports.  Keep one explicit order for the UI and both download formats;
    unknown diagnostic columns are retained after the canonical columns.
    """
    if not isinstance(dataframe, pd.DataFrame):
        return pd.DataFrame()
    result = _sanitize_index_column_collision(dataframe.copy())
    result = _ensure_required_audit_columns(result)
    result = result.drop(columns=list(REMOVED_MIDDLE_COLUMNS), errors="ignore")
    preferred = [
        "Symbol",
        STRATEGY_DECISION_COLUMN,
        "Hourly 4 Entry",
        "Hourly Selection Rank",
        "Hourly Entry Origin",
        "Hourly Selected Count",
        "Strategy Hit Count",
        "Best Strategy Score",
        "Near Entry Score",
        "Hourly Selection Score",
        "Suggested TP",
        "Suggested SL",
        "Suggested TP Price",
        "Suggested SL Price",
        "24H Historical Range",
        "24H Range P85",
        "24H Volatility Move",
        "24H TP Distance",
        "24H SL Distance",
        "TP Target Horizon Hours",
        "24H TP Confidence",
        "Suggested TP Pips",
        "Suggested SL Pips", "24H Estimated Net Pip Potential", "24H ROMAD Proxy",
        "Preferred TP Horizon", "Expected TP Hours", "TP Median Reach Hours", "TP P75 Reach Hours",
        "TP First Rate", "SL First Rate", "SL Rebound To TP Rate", "SL Rebound Sample Count",
        "Required Structural SL", "Allowed Maximum SL", "SL Risk Cap Passed", "SL Reject Reason",
        "SL Structural Quality Score", "SL Liquidity Safety Score", "Suggested SL Quality Score",
        "Nearest TP Barrier Price", "TP Barrier Distance", "TP Barrier Strength", "TP Beyond Barrier",
        "TP Barrier Quality Passed", "TP Quality Score", "SL Quality Score", "TP/SL Pair Quality Score",
        "TP/SL Quality Level", "TP/SL Quality Reason", "TP/SL Sample Count", "TP/SL Engine",
        "Max Hold Hours",
        "Time Exit Hours",
        "Exit Scenario",
        MIDDLE_AGE_RANK_COLUMN,
        *MONTHLY_METADATA,
        *STRATEGY_EXPORT_COLUMNS,
        *STRATEGY_SCORE_COLUMNS.values(),
        "Lower Regime Bias",
        "Middle Regime Bias",
        "Higher Standard Regime Bias",
        CANDLE_AGE_COLUMN,
        STARTING_PRICE_COLUMN,
        "Hour",
        RAS_DECISION_COLUMN,
        CANDLE_STATISTICS_COLUMN,
        AVG_REGIME_CANDLE_COLUMN,
        COMPLETED_SAMPLE_DISPLAY_COLUMN,
        "Middle Standard Regime State",
        "Lower Standard Regime State",
        "Higher Standard Regime State",
        "Completed Candle",
        "Timeframe",
        *AUDIT_OHLC_COLUMNS,
    ]
    if datetime_first and "Datetime" in result.columns:
        preferred = ["Symbol"] + (["Datetime"] if "Datetime" in result.columns else []) + [c for c in preferred if c != "Symbol"]
    ordered = [column for column in preferred if column in result.columns]
    remaining = [column for column in result.columns if column not in ordered]
    return result[ordered + remaining].copy()


# ============================================================================
# Current Middle download
# ============================================================================

def render_middle_regime_download_button(
    st: Any,
    middle_age: pd.DataFrame,
) -> None:

    if (
        not isinstance(
            middle_age,
            pd.DataFrame,
        )
        or middle_age.empty
    ):
        return

    middle_age = _canonical_middle_export_frame(_hourly_entry_export(middle_age))

    # ----------------------------------------------------------------------
    # CSV — always render this independently of optional Excel support.
    # ----------------------------------------------------------------------

    try:
        csv = middle_age.to_csv(
            index=False,
            encoding="utf-8",
        )
    except Exception as exc:
        st.error(f"Middle Standard CSV could not be prepared: {type(exc).__name__}: {exc}")
        csv = None

    if csv is not None:

        st.download_button(
            label=(
                "📥 Download Middle Standard Regime Ranking CSV"
            ),
            data=csv,
            file_name=(
                "middle_standard_regime_ranking.csv"
            ),
            mime="text/csv",
            key=(
                "download_middle_standard_regime_csv"
            ),
            use_container_width=True,
        )

    # ----------------------------------------------------------------------
    # Colored Excel
    # ----------------------------------------------------------------------

    try:
        xlsx = _dataframe_to_excel(
            middle_age,
            "Middle Regime Ranking",
        )
    except Exception as exc:
        state_error = f"{type(exc).__name__}: {exc}"
        xlsx = None
        st.warning(f"Colored Excel is unavailable for this render: {state_error}")

    if xlsx is not None:

        st.download_button(
            label=(
                "🎨 Download Middle Standard Regime Colored Excel"
            ),
            data=xlsx,
            file_name=(
                "middle_standard_regime_ranking.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key=(
                "download_middle_standard_regime_xlsx"
            ),
            use_container_width=True,
        )


# ============================================================================
# Main render
# ============================================================================


# ============================================================================
# Cycle 12 -- entry-check banner + time columns (above Middle ranking table).
# ONE condition: core.cycle12_best.is_entry_check_time / check_time_status.
# The banner never breaks the page: any failure degrades to a small caption.
# ============================================================================

def _best_n_label(system_id):
    """Verified position-sizing Best N for a system id, as display text.

    Source of truth: core.signal_mode.best_n_for_system (the winners'
    sizing values from Report Book V3). Systems without a verified
    value show an em dash rather than an unverified number.
    """
    try:
        from core.signal_mode import best_n_for_system
        n = best_n_for_system(system_id)
    except Exception:
        n = None
    if not n:
        return "\u2014"
    try:
        # 2026-10-26: Best N is now a float (full N divided by 3) --
        # display with 2 decimals instead of the raw long float.
        return f"{float(n):.2f}"
    except Exception:
        return str(n)


def _age_text(mins):
    """Human age for a minute count: '45 min ago', '3h 05m ago', '2d 4h ago'."""
    try:
        m = max(0, int(mins))
    except Exception:
        return "\u2014"
    if m < 60:
        return f"{m} min ago"
    if m < 1440:
        return f"{m // 60}h {m % 60:02d}m ago"
    return f"{m // 1440}d {(m % 1440) // 60}h ago"


def _window_header_html(payload, win_ts, age_min, mins_ago, system_id, live_tag):
    """Header line above a cycle signals table.

    Shows the LATEST CHECK time of the stored window (MMT) with NO time
    limit -- the 2-hour expiry was removed on the user's order
    (2026-10-21) -- plus the window's age, when it was evaluated, the
    symbol count and the system's verified Best N.
    """
    try:
        mmt_ts = win_ts + pd.Timedelta(hours=6, minutes=30)
        check_txt = mmt_ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        check_txt = str(payload.get("window_mmt", "\u2014"))
    return (
        "<div style='font-size:13px;color:#334155;margin:-6px 0 8px 0;'>"
        f"Latest check <b>{check_txt} MMT</b> \u00b7 {_age_text(age_min)} \u00b7 "
        f"evaluated {_age_text(mins_ago)} \u00b7 "
        f"{payload.get('n_symbols', '\u2014')} symbols \u00b7 "
        f"Best N <b>{_best_n_label(system_id)}</b>{live_tag}</div>"
    )


def _cycle12_latest_candle(middle_age):
    """Newest completed-candle timestamp found in the ranking frame, or None."""
    try:
        for col in ("signal_available_at", "signal_at", "Datetime", "check_at"):
            if col in middle_age.columns:
                s = pd.to_datetime(middle_age[col], utc=True, errors="coerce").dropna()
                if len(s):
                    return s.max()
    except Exception:
        return None
    return None


def _cycle12_next_check(now_utc):
    """Next entry-window time (H:00 UTC) at/after now, over the ACTIVE system's hours."""
    try:
        from core.signal_mode import next_entry_time
        return next_entry_time(now_utc)
    except Exception:
        pass
    try:
        from core.signal_mode import active_check_hours
        ALL_CHECK_HOURS = active_check_hours()
    except Exception:
        try:
            from core.cycle12_best import ALL_CHECK_HOURS
        except Exception:
            ALL_CHECK_HOURS = (6, 10, 11, 12, 13, 18)
    cand = []
    base = now_utc.replace(second=0, microsecond=0)
    for day_off in (0, 1, 2, 3):
        day = (base + pd.Timedelta(days=day_off)).normalize()
        if day.weekday() >= 5:
            continue
        for h in ALL_CHECK_HOURS:
            ts = day + pd.Timedelta(hours=h)
            if ts >= base:
                cand.append(ts)
    return min(cand) if cand else None


def _render_cycle12_check_banner(st, candle_age_txt=None):
    """Light entry-window banner above the Cycle 22 signals table.

    Entry windows are H:00:00-H:04:59 UTC on the active system's hours
    (cycle22: 10/11/13/18 -> 16:30/17:30/19:30/00:30 MMT). The backtest
    enters at the H:00 candle open, so the banner, clocks and countdown
    all follow H:00 -- never H:30.

    candle_age_txt: optional precomputed "X old" string; when None the
    box shows a neutral placeholder instead of rendering empty.
    """
    try:
        import datetime as _dt
        import pandas as _pd
        from core.signal_mode import (
            active_system, is_active_check_time, next_entry_time,
            entry_windows_mmt, ENTRY_WINDOW_MINUTES,
        )
        now = _dt.datetime.now(_dt.timezone.utc)
        now_pd = _pd.Timestamp(now)
        in_window = bool(is_active_check_time(now_pd))
        sys_name = {"cycle22": "Cycle 22", "cycle18": "Cycle 18",
                    "ft-c01": "FT-C01", "cycle24": "Cycle 24"}.get(active_system(), active_system())

        def _mmt(ts):
            t = _pd.Timestamp(ts)
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            return (t.tz_convert("UTC") + _pd.Timedelta(hours=6, minutes=30)).tz_localize(None)

        mmt_now = _mmt(now_pd).strftime("%H:%M")
        mmt_date = _mmt(now_pd).strftime("%m-%d")
        utc_now = now_pd.strftime("%H:%M")

        # Candle-age box: driven by the caller (Cycle 22 H1 fetch); never
        # renders empty -- falls back to a neutral placeholder.
        age_txt = str(candle_age_txt) if candle_age_txt else "—"
        try:
            stale = bool(age_txt.endswith("old") and float(age_txt.split("m")[0]) > 90)
        except Exception:
            stale = False

        if in_window:
            t = now_pd.tz_localize(None) if now_pd.tzinfo is not None else now_pd
            window_end = t.replace(second=0, microsecond=0) + _pd.Timedelta(minutes=ENTRY_WINDOW_MINUTES)
            left = window_end - t.replace(tzinfo=None)
            left_s = max(0, int(left.total_seconds()))
            title, title_bg, title_bd = ("🟢 ENTER NOW", "#dcfce7", "#16a34a")
            status_box = (f"<b>🟢 ENTER NOW</b><br><span style='font-size:11px;'>"
                          f"window ends in {left_s // 60:02d}:{left_s % 60:02d}</span>")
        else:
            nxt = next_entry_time(now_pd)
            if nxt is not None:
                nxt_mmt = _mmt(nxt.tz_localize("UTC")).strftime("%H:%M")
                delta = nxt.tz_localize("UTC") - now_pd
                s = max(0, int(delta.total_seconds()))
                cd = f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
                status_box = (f"<b>⚪ NEXT ENTRY</b><br><span style='font-size:11px;'>"
                              f"{nxt_mmt} MMT · in {cd}</span>")
            else:
                status_box = "<b>⚪ NEXT ENTRY</b><br><span style='font-size:11px;'>—</span>"
            title, title_bg, title_bd = ("⚪ WAITING FOR ENTRY WINDOW", "#f1f5f9", "#64748b")

        age_box = (f"📊 <b>{age_txt}</b>" if not stale
                   else f"⚠️ <b>{age_txt}</b><br><span style='font-size:11px;'>stale — refresh</span>")
        try:
            from core.signal_mode import best_n_for_system as _best_n_fn
            _bn_val = _best_n_fn(active_system())
        except Exception:
            _bn_val = None
        # 2026-10-26: Best N is a float (N divided by 3) -- 2 decimals.
        try:
            _bn_txt = f"{float(_bn_val):.2f}" if _bn_val else "\u2014"
        except Exception:
            _bn_txt = str(_bn_val) if _bn_val else "\u2014"
        bestn_box = (f"\U0001f3af <b>Best N {_bn_txt}</b><br>"
                     f"<span style='font-size:11px;'>position sizing</span>")
        box = ("<div style='background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;"
               "padding:6px 10px;text-align:center;min-width:86px;flex:1 1 0;'>"
               "<span style='font-size:13px;color:#0f172a;'>{}</span></div>")
        st.markdown(
            f"<div style='background:{title_bg};border:1px solid {title_bd};border-radius:10px;"
            f"padding:10px 12px;margin:6px 0 8px 0;'>"
            f"<div style='font-size:16px;font-weight:800;color:#0f172a;margin-bottom:8px;'>{title}"
            f"<span style='font-weight:400;font-size:12px;color:#475569;'> · {sys_name}</span></div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:6px;'>"
            + box.format(status_box)
            + box.format(f"🇲🇲 <b>{mmt_now}</b> MMT<br><span style='font-size:11px;'>{mmt_date}</span>")
            + box.format(f"🌍 <b>{utc_now}</b> UTC")
            + box.format(age_box)
            + box.format(bestn_box)
            + f"</div></div>",
            unsafe_allow_html=True,
        )
        st.caption("Entry windows (MMT): " + " · ".join(entry_windows_mmt())
                   + " — entries at the candle open, backtest-matched.")
    except Exception:
        st.caption("Entry-window banner unavailable (time helpers failed to load).")


def _cycle12_add_time_columns(frame):
    """Add Myanmar Time / MetaTrader Time / Entry Check Time (Yes/No)
    columns to a ranking-table copy. Per-row time comes from the row's
    own check/signal timestamp when present, else now (UTC)."""
    out = frame.copy()
    try:
        from core.cycle12_best import is_entry_check_time, to_myanmar, to_metatrader
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        stamps = None
        for col in ("check_at", "signal_available_at", "signal_at", "Datetime"):
            if col in out.columns:
                stamps = pd.to_datetime(out[col], utc=True, errors="coerce")
                break
        if stamps is None or stamps.isna().all():
            stamps = pd.Series([pd.Timestamp(now)] * len(out), index=out.index)
        stamps = stamps.fillna(pd.Timestamp(now))
        out["Myanmar Time"] = [to_myanmar(s).strftime("%Y-%m-%d %H:%M") for s in stamps]
        out["MetaTrader Time"] = [to_metatrader(s).strftime("%Y-%m-%d %H:%M") for s in stamps]
        try:
            from core.signal_mode import is_active_check_time as _win_check
            out["Entry Check Time (Yes/No)"] = [
                "Yes" if _win_check(s) else "No" for s in stamps
            ]
        except Exception:
            out["Entry Check Time (Yes/No)"] = [
                "Yes" if is_entry_check_time(s) else "No" for s in stamps
            ]
    except Exception:
        out["Myanmar Time"] = "n.a."
        out["MetaTrader Time"] = "n.a."
        out["Entry Check Time (Yes/No)"] = "n.a."
    return out


_CYCLE22_PANEL_SYMBOLS = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CHFJPY", "EURAUD",
    "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD", "GBPJPY",
    "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
)


def _normalize_c22_frame(df):
    from core.check_candle_runtime import normalize_ohlc
    return normalize_ohlc(df, min_bars=50)


def _render_symbols_loaded_box(st, context):
    """Small clean box: how many symbols were successfully loaded."""
    try:
        loaded = list(context.completed_symbols or context.loaded_symbols or [])
        configured = list(getattr(context, "configured_symbols", None) or [])
        failed = context.failed_symbols if isinstance(
            getattr(context, "failed_symbols", None), dict) else {}
        n_ok, n_cfg, n_fail = len(loaded), len(configured), len(failed)
        if n_cfg:
            txt = f"📊 <b>{n_ok}/{n_cfg}</b> symbols with loaded history"
        else:
            txt = f"📊 <b>{n_ok}</b> symbols with loaded history"
        if n_fail:
            txt += f" <span style='color:#b91c1c;'>({n_fail} failed)</span>"
        st.markdown(
            "<div style='background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;"
            "padding:5px 12px;margin:0 0 6px 0;display:inline-block;'>"
            f"<span style='font-size:13px;color:#0f172a;'>{txt}</span></div>",
            unsafe_allow_html=True,
        )
    except Exception:
        return


# Cycle 24 (R4A01) parallel state -- own keys so the Cycle 22 path is untouched.
try:
    # Single source of truth: core/cycle24_best.py (R4A01: hours 15/17/18 UTC).
    from core.cycle24_best import CYCLE24_CHECK_HOURS as _C24_CHECK_HOURS
except Exception:
    _C24_CHECK_HOURS = (15, 17, 18)


def _c22_window_mmt_label(hour_utc):
    """MMT 'HH:MM' label for an entry-window UTC hour (UTC+6:30)."""
    m = (int(hour_utc) * 60 + 390) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _fetch_c22_frames(state, need_candles=None):
    from core.check_candle_runtime import fetch_check_frames
    return fetch_check_frames(state, _CYCLE22_PANEL_SYMBOLS, need_candles)


def _require_check_frames(frames, need):
    needed = set(pd.Timestamp(t) for t in need)
    if any(sym not in frames or not needed.issubset(frames[sym].index)
           for sym in _CYCLE22_PANEL_SYMBOLS):
        raise ValueError("check_candles_incomplete")


def _require_evaluator_status(frame):
    if isinstance(frame, pd.DataFrame) and frame.attrs.get("status"):
        raise ValueError("feature_data_incomplete")


def _c22_signals_to_display(entries):
    """Add human TP/SL price columns to an evaluated signals frame."""
    import pandas as _pd
    from core.cycle12_best import pip_size as _pip_size
    if entries is None or not isinstance(entries, _pd.DataFrame) or entries.empty:
        return _pd.DataFrame(columns=["Quick look", "Symbol", "Direction", "Strategy", "Entry", "TP", "SL", "Score"])
    rows = []
    for _, r in entries.iterrows():
        try:
            sym = str(r["symbol"]).upper()
            d = str(r["direction"]).upper()
            entry = float(r["entry_px"])
            tp_p = float(r["tp_pips"])
            sl_p = float(r["sl_pips"])
            score = float(r.get("score", 0.0))
            pip = _pip_size(sym)
            if d == "BUY":
                tp_x, sl_x = entry + tp_p * pip, entry - sl_p * pip
            else:
                tp_x, sl_x = entry - tp_p * pip, entry + sl_p * pip
            dec = 3 if pip >= 0.01 else 5
            strat = "\u2014"
            for _col in ("equation", "strategy", "Equation ID", "strategy_id"):
                try:
                    _v = r.get(_col)
                except Exception:
                    _v = None
                if _v is not None and str(_v).strip() not in ("", "nan", "None"):
                    strat = str(_v)
                    break
            _tp_disp = round(tp_x, dec)
            _sl_disp = round(sl_x, dec)
            rows.append({
                # Front quick-look column (user format, 2026-10-22):
                # EURUSD-B-T<tp>,S<sl> -- symbol, bias B/S, TP after T, SL after S.
                "Quick look": (f"{sym}-{'B' if d == 'BUY' else 'S'}-"
                               f"T{_tp_disp:.{dec}f},S{_sl_disp:.{dec}f}"),
                "Symbol": sym,
                "Direction": d,
                "Strategy": strat,
                "Entry": round(entry, dec),
                "TP": _tp_disp,
                "SL": _sl_disp,
                "Score": round(score, 1),
            })
        except Exception:
            continue
    return _pd.DataFrame(rows, columns=["Quick look", "Symbol", "Direction", "Strategy", "Entry", "TP", "SL", "Score"])


def _entry_row_colors(df):
    """Styler that colors a WHOLE entry row: light blue for BUY, light
    red for SELL (user order 2026-10-26). A row counts as an entry row
    when it carries an Entry price and a Buy/Sell direction; other rows
    stay uncolored. Used with st.table so the text renders as real HTML
    (the canvas grid smeared/overlapped text on the user's screen)."""
    def _row_style(row):
        try:
            d = str(row.get("Direction", "")).strip().lower()
            e = str(row.get("Entry", "")).strip()
            if e not in ("", "\u2014", "-", "None", "nan") and d == "buy":
                return ["background-color: #cfe8ff"] * len(row)
            if e not in ("", "\u2014", "-", "None", "nan") and d == "sell":
                return ["background-color: #ffd6d6"] * len(row)
        except Exception:
            pass
        return [""] * len(row)
    return df.style.apply(_row_style, axis=1)




_RANKING_COLUMNS = ["Quick look", "Rank", "Symbol", "Status", "Direction",
                    "Entry", "Signal close", "TP", "SL", "Score", "Equation"]


def _c22_build_check_ranking(sig, entries, frames, need):
    """Full per-symbol ranking for one evaluated check window.

    One row per evaluated symbol (every symbol in ``frames``), ordered the
    way the engine already orders candidates: the selected entry first,
    then the other firing candidates by score, then symbols whose entry
    condition was NOT met, then symbols whose candles were missing. Fired
    rows carry entry/TP/SL plus the Quick-look string; unmet rows stay
    present and explicitly marked, so the panel NEVER collapses to a bare
    text line (user order 2026-10-22, round 2). Pure display computation
    on already-fetched frames -- no provider calls, no re-evaluation.
    """
    import pandas as _pd
    cols = _RANKING_COLUMNS
    try:
        frames = frames or {}
        need_set = set()
        for c in (need or []):
            try:
                need_set.add(_pd.Timestamp(c).tz_localize(None))
            except Exception:
                pass
        evaluable, no_data = [], []
        for sym in _CYCLE22_PANEL_SYMBOLS:
            f = frames.get(sym)
            ok = False
            try:
                ok = f is not None and need_set.issubset(
                    set(_pd.Timestamp(t).tz_localize(None) for t in f.index))
            except Exception:
                ok = False
            (evaluable if ok else no_data).append(str(sym).upper())
        # Best firing candidate per symbol (highest score, engine order).
        best = {}
        if isinstance(sig, _pd.DataFrame) and not sig.empty \
                and "symbol" in sig.columns:
            _s = sig
            try:
                _s = sig.sort_values("score", ascending=False,
                                     kind="mergesort")
            except Exception:
                pass
            for _, r in _s.iterrows():
                s = str(r.get("symbol", "")).upper()
                if s and s not in best:
                    best[s] = r
        selected = []
        if isinstance(entries, _pd.DataFrame) and not entries.empty:
            for _, r in entries.iterrows():
                s = str(r.get("symbol", "")).upper()
                if s:
                    selected.append(s)
        selected_set = set(selected)
        # Display values (entry/TP/SL/Quick look) via the same formatter
        # as the signals table, for consistent prices everywhere.
        cand_rows = {}
        if best:
            _disp = _c22_signals_to_display(_pd.DataFrame(list(best.values())))
            if isinstance(_disp, _pd.DataFrame):
                for _, dr in _disp.iterrows():
                    cand_rows[str(dr.get("Symbol", "")).upper()] = dr
        rows = []
        rank = [0]

        def _push(sym, status):
            rank[0] += 1
            dr = cand_rows.get(sym)
            r = best.get(sym)
            f = frames.get(sym)
            entry_price = signal_close = "—"
            if f is not None and need_set and need_set.issubset(f.index):
                entry_price = float(f.loc[max(need_set), "Open"])
                signal_close = float(f.loc[min(need_set), "Close"])
            rows.append({
                "Rank": rank[0],
                "Symbol": sym,
                "Status": status,
                "Quick look": (str(dr.get("Quick look")) if dr is not None else "\u2014"),
                "Direction": (str(dr.get("Direction")) if dr is not None else "\u2014"),
                "Entry": (dr.get("Entry") if dr is not None else entry_price),
                "Signal close": signal_close,
                "TP": (dr.get("TP") if dr is not None else "\u2014"),
                "SL": (dr.get("SL") if dr is not None else "\u2014"),
                "Score": (dr.get("Score") if dr is not None else (0.0 if isinstance(entry_price, float) else "—")),
                "Equation": (str(r.get("equation")) if r is not None else "\u2014"),
            })

        for s in selected:
            _push(s, "\u2705 ENTRY")
        for s in sorted((s for s in best if s not in selected_set),
                        key=lambda s: -float(best[s].get("score", 0.0) or 0.0)):
            _push(s, "Fired \u2014 not selected")
        for s in evaluable:
            if s not in best:
                _push(s, "\u2014 No entry")
        for s in no_data:
            if s not in best:
                _push(s, "\u26a0 No data")
        return _pd.DataFrame(rows, columns=cols)
    except Exception:
        return _pd.DataFrame(columns=cols)


def _eval_history_db_path():
    """Persistent store for signal evaluation history (last 24h tables).

    Lives in the app's data area next to the candle repository DB, so the
    history survives app restarts. FOREX_EVAL_HISTORY_DB overrides the
    location (used by tests)."""
    import os as _os
    from pathlib import Path as _Path
    _env = _os.environ.get("FOREX_EVAL_HISTORY_DB")
    if _env:
        return _Path(_env)
    return (_Path(__file__).resolve().parents[1] / "data"
            / "signal_eval_history.sqlite3")


def _record_eval_history(sysname, payload, replace=True):
    """Persist one evaluation result (cycle, check window, x/20 evaluated,
    fired entries with Quick-look strings) into the local history store.
    Local sqlite only -- no provider calls. Never raises."""
    try:
        import json as _json
        import sqlite3 as _sq
        import pandas as _pd
        if not isinstance(payload, dict) or payload.get("window_utc") is None:
            return
        win_iso = _pd.Timestamp(payload["window_utc"]).tz_localize(None).isoformat()
        try:
            ev_iso = _pd.Timestamp(
                payload.get("evaluated_at_utc")).tz_localize(None).isoformat()
        except Exception:
            ev_iso = ""

        def _num(v):
            try:
                return float(v)
            except Exception:
                return v

        entries = []
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            for _, r in disp.iterrows():
                try:
                    entries.append({
                        "symbol": str(r.get("Symbol", "")),
                        "direction": str(r.get("Direction", "")),
                        "entry": _num(r.get("Entry")),
                        "tp": _num(r.get("TP")),
                        "sl": _num(r.get("SL")),
                        "quick": str(r.get("Quick look", "")),
                    })
                except Exception:
                    continue

        def _int_or_none(v):
            try:
                return int(v)
            except Exception:
                return None

        path = _eval_history_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = _sq.connect(str(path), timeout=10)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS signal_eval_history ("
                "cycle TEXT NOT NULL, window_utc TEXT NOT NULL, "
                "window_mmt TEXT, evaluated_at_utc TEXT, n_symbols INTEGER, "
                "n_evaluable INTEGER, entries_json TEXT, "
                "PRIMARY KEY (cycle, window_utc))")
            _verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
            conn.execute(
                _verb + " INTO signal_eval_history"
                " (cycle, window_utc, window_mmt, evaluated_at_utc,"
                "  n_symbols, n_evaluable, entries_json)"
                " VALUES (?,?,?,?,?,?,?)",
                (str(sysname), win_iso, str(payload.get("window_mmt", "")),
                 ev_iso, _int_or_none(payload.get("n_symbols")),
                 _int_or_none(payload.get("n_evaluable")),
                 _json.dumps(entries)))
            import datetime as _dt
            _cut = (_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                    - _dt.timedelta(hours=48)).isoformat()
            conn.execute(
                "DELETE FROM signal_eval_history WHERE window_utc < ?", (_cut,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _load_eval_history(sysname, hours=24):
    """History rows for one system from the persistent store, newest
    check first. Local read only -- no provider calls."""
    try:
        import datetime as _dt
        import json as _json
        import sqlite3 as _sq
        path = _eval_history_db_path()
        if not path.exists():
            return []
        _cut = (_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
                - _dt.timedelta(hours=hours)).isoformat()
        conn = _sq.connect(str(path), timeout=10)
        try:
            cur = conn.execute(
                "SELECT window_utc, n_symbols, n_evaluable, entries_json "
                "FROM signal_eval_history WHERE cycle = ? AND window_utc >= ? "
                "ORDER BY window_utc DESC", (str(sysname), _cut))
            out = []
            for win_iso, n_sym, n_ev, ej in cur.fetchall():
                try:
                    entries = _json.loads(ej or "[]")
                except Exception:
                    entries = []
                out.append({"window_utc": win_iso, "n_symbols": n_sym,
                            "n_evaluable": n_ev, "entries": entries})
            return out
        finally:
            conn.close()
    except Exception:
        return []


def _backfill_eval_history_from_state(state):
    """Seed the persistent history from payloads already held in session
    state (each system's stored window + last-entry companion) when the
    store has no row for them yet."""
    try:
        for _sysname, _panel in _SIGNAL_PANELS.items():
            _p = state.get(_panel["state_key"])
            if isinstance(_p, dict):
                _record_eval_history(_sysname, _p, replace=False)
            _le = state.get(_panel["state_key"] + ":last_entry")
            if isinstance(_le, dict) and _le.get("window_utc") is not None:
                _record_eval_history(_sysname, {
                    "window_utc": _le.get("window_utc"),
                    "window_mmt": _le.get("window_mmt"),
                    "signals": _le.get("signals"),
                    "n_evaluable": -1,
                }, replace=False)
    except Exception:
        pass


def _render_eval_history(st, state, sysname):
    """Last-24-hour history table for one system panel: every check
    window in the last 24 hours, how many symbols evaluated (x/20), and
    the fired entries as Quick-look strings -- or an explicit 'no entry'.
    Reads ONLY the persistent local store, so it survives app restarts
    and costs no provider calls."""
    import pandas as _pd
    try:
        _backfill_eval_history_from_state(state)
        rows = _load_eval_history(sysname, hours=24)
        st.markdown("### \U0001F559 Last 24 hours \u2014 every check")
        if not rows:
            st.caption("No checks recorded yet in the last 24 hours \u2014 "
                       "history builds as each window evaluates and is "
                       "kept across app restarts.")
            return
        _disp = []
        for r in rows:
            try:
                _mmt = (_pd.Timestamp(r["window_utc"])
                        + _pd.Timedelta(hours=6, minutes=30))
                _check = _mmt.strftime("%b %d \u00b7 %H:%M")
            except Exception:
                _check = str(r["window_utc"])
            _nev = r.get("n_evaluable")
            _syms = (f"{int(_nev)}/20"
                     if isinstance(_nev, int) and _nev >= 0 else "\u2014/20")
            _ent = r.get("entries") or []
            _res = (" \u00b7 ".join(str(e.get("quick", "")) for e in _ent)
                    if _ent else ("Calculation incomplete" if isinstance(_nev, int) and 0 <= _nev < 20 else "\u2014 no entry"))
            _disp.append({"Check (MMT)": _check, "Symbols": _syms,
                          "Result": _res})
        st.dataframe(_pd.DataFrame(_disp),
                     use_container_width=True, hide_index=True)
    except Exception:
        pass


def _latest_entry_window_utc(now_utc, hours=None):
    """Latest H:00 UTC entry window at/before now (weekdays only).

    Rolls back across weekends: e.g. Monday 00:05 MMT (= Sunday 17:35 UTC)
    returns Friday 18:00 UTC. Returns a naive UTC Timestamp, or None.
    ``hours`` overrides the active system's check hours (Cycle 24 passes
    its own (15, 17, 18)).
    """
    import pandas as _pd
    from core.signal_mode import active_check_hours
    now = _pd.Timestamp(now_utc)
    if now.tzinfo is not None:
        now = now.tz_convert("UTC").tz_localize(None)
    hours = sorted(hours if hours is not None else active_check_hours())
    for day_off in range(0, 8):
        day = (now - _pd.Timedelta(days=day_off)).normalize()
        if day.weekday() >= 5:
            continue
        for h in sorted(hours, reverse=True):
            ts = day + _pd.Timedelta(hours=h)
            if ts <= now:
                return ts
    return None


def _diag_notes(payload):
    """Provider notes from a window evaluation's fetch diagnostics,
    for the data-failure message (fix 2026-10-26): the fetch already
    records WHY each live refresh failed (rate limit, key pool, empty
    response) -- surfacing it turns an invisible failure into a
    readable one instead of a bare 0/20."""
    try:
        diag = (payload or {}).get("diag") or {}
        if diag.get("evaluation_error"):
            return "Calculation error: " + str(diag["evaluation_error"]) + ". Retrying automatically."
        errs = diag.get("live_errors") or []
        if errs:
            return "Provider notes: " + "; ".join(str(e) for e in errs[:4])
        return (f"Fetch sources: cache {diag.get('cache', 0)}/20, "
                f"live {diag.get('live', 0)}/20.")
    except Exception:
        return ""


def _c22_data_loaded(state):
    """True when the shared pipeline reports loaded symbols.

    Cheap gate for the (expensive) provider-chain fetch: with no data
    loaded there is nothing to evaluate.
    """
    try:
        from core.twelve_data_key_pool import TwelveDataKeyPool
        if TwelveDataKeyPool.from_state(state).has_available_key():
            return True
        ctx = get_global_symbol_context(state)
        return len(list(ctx.completed_symbols or ctx.loaded_symbols or [])) > 0
    except Exception:
        return False


def _payload_data_failed(payload):
    """True when a stored payload is a DATA failure (too few symbols had the
    needed candles), as opposed to a genuine no-signal window. Such payloads
    must not block re-evaluation of the same window once data recovers --
    before this check, a 0/20 payload was stored and the panel never retried
    that window (the 2026-10-22 00:30 MMT incident)."""
    try:
        return isinstance(payload, dict) and (int(payload.get("n_evaluable", 0)) < len(_CYCLE22_PANEL_SYMBOLS)
            or bool((payload.get("diag") or {}).get("evaluation_error")))
    except Exception:
        return False


def _force_dashboard_refresh(st, state):
    """'Refresh the dashboard' button action: drop every stored panel
    payload + fail mark (all 12 systems), clear the M15 fetch memos, set the
    force flag the H1 fetch path consumes (provider refresh for all 20
    symbols), and rerun so the visible panel re-evaluates on fresh data."""
    import importlib as _il
    for _sysname, _panel in _SIGNAL_PANELS.items():
        for _key in (_panel["state_key"], _panel["diag_key"], _panel["fail_key"],
                     _panel["state_key"] + ":last_entry"):
            try:
                state.pop(_key, None)
            except Exception:
                pass
    for _modname in ("core.cycle78_best", "core.cycle86_best", "core.cycle87_best",
                     "core.cycle89_best", "core.cycle91_best", "core.cycle93_best",
                     "core.cycle94_best"):
        try:
            _memo = getattr(_il.import_module(_modname), "_M15_FETCH_MEMO", None)
            if isinstance(_memo, dict):
                _memo["ts"] = None
                _memo["frames"] = None
        except Exception:
            pass
    from core.check_candle_runtime import H1_MEMO_KEY, M15_MEMO_KEY
    state.pop(H1_MEMO_KEY, None)
    state.pop(M15_MEMO_KEY, None)
    try:
        from core.cycle78_best import _M15_FETCH_MEMO_BY_SET
        _M15_FETCH_MEMO_BY_SET.clear()
    except Exception:
        pass
    try:
        state["force_signal_refresh"] = True
    except Exception:
        pass
    try:
        st.rerun()
    except Exception:
        pass


def _render_check_time_reminders(st, state):
    """Check-time reminders: CURRENT month only (Myanmar time).

    Times come from each cycle module's own CHECK_HOURS (the entry windows),
    shown in Myanmar time (UTC+6:30) as 'HH:MM-HH:MM'. Every month/time row
    carries a checkbox whose key lives in Streamlit session state -- the
    app's state mechanism -- so ticks survive reruns and page reloads of
    the session."""
    import importlib as _il
    st.markdown("### \u23f0 Check-time reminders")
    st.caption("Tick the check times you want to remind yourself of. "
               "Ticks are saved in the app state and stay ticked.")
    # User order 2026-10-22 (round 2): show ONLY the current calendar
    # month (Myanmar time) -- other months' ticks stay stored in state,
    # just not displayed. The month follows the actual current date.
    try:
        import datetime as _dtr
        _mmt_month = (_dtr.datetime.now(_dtr.timezone.utc)
                      + _dtr.timedelta(hours=6, minutes=30)).month
        _panel_order = [_MONTH_PANEL_ORDER[_mmt_month - 1]]
    except Exception:
        _panel_order = _MONTH_PANEL_ORDER
    for _month_name, _sysname, _nn, _code in _panel_order:
        try:
            _mod = _il.import_module(f"core.cycle{_nn}_best")
            _hours = getattr(_mod, f"CYCLE{_nn}_CHECK_HOURS")
        except Exception:
            continue
        st.markdown(f"**{_month_name} \u2014 Cycle {_nn} ({_code})**")
        for _h in _hours:
            _start = _c22_window_mmt_label(_h)
            _end_min = (int(_h) * 60 + 390 + 4) % 1440
            _label = (f"{_month_name} \u00b7 {_start}-{_end_min // 60:02d}:"
                      f"{_end_min % 60:02d} MMT")
            try:
                st.checkbox(_label, key=f"reminder::{_sysname}::{int(_h):02d}")
            except Exception:
                pass




# ============================================================================
# Cycle 24 (R4A01) signals table -- parallel to the Cycle 22 path above.
# Own session-state keys; the working Cycle 22 code is NOT refactored.


# ============================================================================
# Cycle 26 (C26-33, November-only) signals table.
# Mirrors the Cycle 24 renderer: own session-state keys; the working
# Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================


# ============================================================================
# Cycle 27 (C27-01, December-only) signals table.
# Mirrors the Cycle 26 renderer: own session-state keys; the working
# Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 28 (C28-30, January-only) signals table.
# Mirrors the Cycle 27 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 29 (C29-31, February-only) signals table.
# Mirrors the Cycle 29 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 30 (C30-31, March-only) signals table.
# Mirrors the Cycle 30 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 31 (C31-29, April-only) signals table.
# Mirrors the Cycle 31 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 32 (C32-20, May-only) signals table.
# Mirrors the Cycle 32 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 33 (C33-18, June-only) signals table.
# Mirrors the Cycle 33 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 34 (C34-17, July-only) signals table.
# Mirrors the Cycle 34 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 35 (C35-31, August-only) signals table.
# Mirrors the Cycle 35 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 36 (C36-40, September-only) signals table.
# Mirrors the Cycle 36 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================


# ============================================================================
# Cycle 48 (C48-02, December-only) signals table.
# Mirrors the Cycle 27 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# C48-02 replaced C27-01 as December's system (improvement program).
# ============================================================================





# ============================================================================
# Cycle 42 (C42-18, June-only) signals table.
# C42-18 replaced C33-18 as June's system (improvement program,
# user override promotion).# Mirrors the Cycle 42 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================






# ============================================================================
# Cycle 44 (C44-15, August-only) signals table.
# C44-15 replaced C35-31 as August's system (improvement program,
# user override promotion).# Mirrors the Cycle 44 renderer: own session-state keys; the working
# Cycle 27 / Cycle 26 / Cycle 24 / Cycle 22 code is NOT refactored.
# ============================================================================






# ============================================================================
# Cycle 52 (C52-04, January-only) signals table.
# Mirrors the Cycle 48 renderer: own session-state keys; the working
# earlier cycle code is NOT refactored.
# C52-04 replaced C28-30 as January's system (improvement program 2).
# ============================================================================







# ============================================================================
# Cycle 51 (C51-20, November-only) signals table.
# Mirrors the Cycle 48 renderer: own session-state keys; the working
# earlier cycle code is NOT refactored.
# C51-20 replaced C26-33 as November's system (improvement program 2).
# ============================================================================







# ============================================================================
# Cycle 53 (C53-07, March-only) signals table.
# Mirrors the Cycle 48 renderer: own session-state keys; the working
# earlier cycle code is NOT refactored.
# C53-07 replaced C30-31 as March's system (improvement program 2).
# ============================================================================







# ============================================================================
# Cycle 55 (C55-15, August-only) signals table.
# C55-15 replaced C55-15 as August's system (improvement program 2
# near-miss, promoted by user override after passing the LCT at the
# middle and strict levels). Mirrors the Cycle 44 renderer: own
# session-state keys; the working earlier cycle code is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 56 (C56-15, February-only) signals table.
# C56-15 replaced C29-31 as February's system (follow-up
# round winner: weak 7 vs 11 at 2.5-pip, unseen net@2.5
# +124.8, LCT middle PASS). Mirrors the Cycle 55 renderer:
# own session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 57 (C57-16, April-only) signals table.
# C57-16 replaced C31-29 as April's system (follow-up
# round winner: incumbent 24 equations verbatim + 12
# fresh competitor legs; weak 4 vs 6 at 2.5-pip, LCT
# middle PASS). Mirrors the Cycle 55 renderer: own
# session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 56 (C56-15, February-only) signals table.
# C56-15 replaced C29-31 as February's system (follow-up
# round winner: weak 7 vs 11 at 2.5-pip, unseen net@2.5
# +124.8, LCT middle PASS). Mirrors the Cycle 57 renderer:
# own session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 59 (C59-18, September-only) signals table.
# C59-18 replaced C36-40 as September's system (follow-up
# round winner: incumbent 24 equations verbatim +
# Alligator-ordering rerank overlay; weak 1 vs 8 at
# 2.5-pip). Mirrors the Cycle 55 renderer: own
# session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 56 (C56-15, February-only) signals table.
# C56-15 replaced C29-31 as February's system (follow-up
# round winner: weak 7 vs 11 at 2.5-pip, unseen net@2.5
# +124.8, LCT middle PASS). Mirrors the Cycle 59 renderer:
# own session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 57 (C57-16, April-only) signals table.
# C57-16 replaced C31-29 as April's system (follow-up
# round winner: incumbent 24 equations verbatim + 12
# fresh competitor legs; weak 4 vs 6 at 2.5-pip, LCT
# middle PASS). Mirrors the Cycle 59 renderer: own
# session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================




# ============================================================================
# Cycle 56 (C56-15, February-only) signals table.
# C56-15 replaced C29-31 as February's system (follow-up
# round winner: weak 7 vs 11 at 2.5-pip, unseen net@2.5
# +124.8, LCT middle PASS). Mirrors the Cycle 57 renderer:
# own session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 65 (C65-01, June-only) signals table.
# C65-01 replaced C42-18 as June's system (LCT-fix
# round: C42-18's 24 equations verbatim + 6 fresh
# ASI/Laguerre legs that only preempt TREND
# fallbacks; LCT strict pass vs C42-18, promoted by
# user override). Mirrors the Cycle 59 renderer: own
# session-state keys; the working earlier cycle code
# is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 71 (C71-04, December-only) signals table.
# C71-04 replaced C48-02 as December's system
# (LCT-fix round: C48-02's 30 equations verbatim +
# 4 fresh GMMA/Chaikin/Stochastic-RSI/shadow legs;
# LCT middle pass P 99.98%, clean promotion).
# Mirrors the Cycle 59 renderer: own session-state
# keys; the working earlier cycle code is NOT
# refactored.
# ============================================================================



# ============================================================================
# Cycle 70 (C70-07, November-only) signals table.
# C70-07 replaced C51-20 as November's system
# (LCT-fix round: 24 fresh Ehlers Cyber Cycle /
# Bandpass + TSI + Random Walk Index equations +
# 9 TREND fallbacks; LCT pass at BOTH levels,
# promoted by user override). Mirrors the Cycle 59
# renderer: own session-state keys; the working
# earlier cycle code is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 64 (C64-09, May-only) signals table.
# C64-09 replaced C32-20 as May's system
# (LCT-fix round: C32-20's 24 equations verbatim +
# 6 fresh AO/CMO/Alligator/Qstick/Yang-Zhang legs;
# LCT pass at BOTH levels, promoted by user
# override). Mirrors the Cycle 59 renderer: own
# session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 69 (C69-07, October-only) signals table.
# C69-07 replaced R4A01 (cycle24) as October's APP
# default (live signal crons keep R4A01 unchanged).
# LCT-fix round: R4A01's 24 equations verbatim + 9
# fresh tail-penalised legs; paired LCT P 100.00%,
# promoted by Muse's decision under the user's
# standing rule. Mirrors the Cycle 59 renderer: own
# session-state keys; earlier code NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 63 (C63-04, April-only) signals table.
# C63-04 replaced C57-16 as April's system
# (LCT-fix round: C57-16's 36 equations verbatim +
# 6 fresh ZigZag swing-structure legs; weak 4 -> 0,
# LCT PASS at middle AND strict -- clean promotion).
# Mirrors the Cycle 59 renderer: own session-state
# keys; the working earlier cycle code is NOT
# refactored.
# ============================================================================



# ============================================================================
# Cycle 66 (C66-08, July-only) signals table.
# C66-08 replaced C34-17 as July's system
# (LCT-fix round: C34-17's equations with a Guppy-
# ribbon gate on the TREND fallbacks + 3 fresh
# EURNZD legs; LCT middle PASS -- clean promotion).
# Mirrors the Cycle 59 renderer: own session-state
# keys; the working earlier cycle code is NOT
# refactored.
# ============================================================================



# ============================================================================
# Cycle 62 (C62-10, March-only) signals table.
# C62-10 replaced C53-07 as March's system
# (LCT-fix round: C30-31's 24 equations walked
# PLAIN -- no G013 rerank -- + 5 fresh skew /
# Laguerre / Mass Index / kurtosis / Elder legs;
# LCT middle PASS -- clean promotion). Mirrors the
# Cycle 59 renderer: own session-state keys; the
# working earlier cycle code is NOT refactored.
# ============================================================================



# ============================================================================
# Cycle 60 (C60-03, January-only) signals table.
# C60-03 replaced C52-04 as January's system
# (LCT-fix round: incumbent 24 equations walked
# PLAIN -- no H012 rerank -- + 8 fresh GMMA / TSF /
# Tillson-T3 compete legs; paired LCT P 98.15%,
# promoted by Muse's decision). Mirrors the Cycle
# 59 renderer: own session-state keys; the working
# earlier cycle code is NOT refactored.
# ============================================================================
_C60_SIG_STATE_KEY = "cycle60_signals_latest_v1"
_C60_SIG_AGE_KEY = "cycle60_candle_age_txt"
_C60_SIG_DIAG_KEY = "cycle60_signals_diag_v1"
_C60_SIG_FAIL_KEY = "cycle60_signals_fail_v1"


def _evaluate_c60_window(state, hour_utc, day=None):
    """Evaluate the 32 Cycle 60 (C60-03) equations for one entry window.

    Calls core.cycle60_best directly (not the signal router) so the result
    is always the C60 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle60_best import evaluate_cycle60_signals, select_cycle60_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C60_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C60_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle60_signals(frames, check_label)
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle60_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle60", payload)
        try:
            state[_C60_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c60_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C60 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C60_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c60_mark_fail(window_utc, state):
    """Record a failed C60 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C60_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C60_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle60_signals_table(st, state):
    """Cycle 60 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C60 entry window <= now (hours 11/13/17 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle60_best import CYCLE60_CHECK_HOURS as _C60_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C60_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C60_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c60_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 60 signals..."):
                new_payload = _evaluate_c60_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c60_mark_fail(latest_win, state)
            else:
                _c60_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 60 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 60 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C60_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 60 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle60", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C60_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 60 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C60_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 60 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 60 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C60_SIG_STATE_KEY) if isinstance(state.get(_C60_SIG_STATE_KEY), dict) else None


def render_cycle60_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 60 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle60_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 60 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 60 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle60_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle60")
            st.download_button(
                label="\U0001F4E5 Download Cycle 60 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle60_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 60B (BRIEF23 C20_STACK IMPROVED, January BEST) signals table.
# Priority: 1st = this system (C60-03 + C10 FB breadth veto + FB
# SL x0.60 + 24h stall cut + C17 score-gated dual-pick); 2nd (only
# when 1st is silent at a check) = old Cycle 60 (C60-03) via the
# COMBINED panel. Validated BRIEF23: DISC n355 net +1984.54 win
# 95.21% leftover 64.23; AUDIT n101 net +550.18 leftover 67.50;
# app replay EXACT 2026-10-26 (FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md).
# ============================================================================
_C60B_SIG_STATE_KEY = "cycle60b_signals_latest_v1"
_C60B_SIG_AGE_KEY = "cycle60b_candle_age_txt"
_C60B_SIG_DIAG_KEY = "cycle60b_signals_diag_v1"
_C60B_SIG_FAIL_KEY = "cycle60b_signals_fail_v1"


def _evaluate_c60b_window(state, hour_utc, day=None):
    """Evaluate the 32 Cycle 60B (C20_STACK) equations for one entry window.

    Calls core.cycle60b_best directly (not the signal router) so the result
    is always the C60B system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle60b_best import evaluate_cycle60b_signals, select_cycle60b_entries
    from core.cycle60b_best import fetch_cycle60b_m15_frames
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C60B_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C60B_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle60b_signals(
                frames, check_label,
                m15_frames=fetch_cycle60b_m15_frames())
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle60b_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle60b", payload)
        try:
            state[_C60B_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c60b_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C60B window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C60B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c60b_mark_fail(window_utc, state):
    """Record a failed C60B evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C60B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C60B_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle60b_signals_table(st, state):
    """Cycle 60B signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C60B entry window <= now (hours 11/13/17 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle60b_best import CYCLE60B_CHECK_HOURS as _C60B_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C60B_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C60B_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c60b_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 60B signals..."):
                new_payload = _evaluate_c60b_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c60b_mark_fail(latest_win, state)
            else:
                _c60b_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 60B signals \u2014 January IMPROVED system (BRIEF23 C20_STACK)")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 60B entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C60B_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 60B evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle60b", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C60B_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 60B equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C60B_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 60B equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 60B equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C60B_SIG_STATE_KEY) if isinstance(state.get(_C60B_SIG_STATE_KEY), dict) else None


def render_cycle60b_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 60B signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle60b_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 60B CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 60B signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle60b_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle60B")
            st.download_button(
                label="\U0001F4E5 Download Cycle 60B signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle60b_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# ============================================================================
# Cycle 67 (C67-04, August-only) signals table.
# C67-04 replaced C55-15 as August's default
# (LCT-fix round: C55-15 core FROZEN -- core hours
# delegate to cycle55 -- + 8 fresh supplement legs
# at NEW hours 1 and 18 UTC; up to 2 entries/check;
# paired LCT structurally capped, promoted by
# Muse's decision). Mirrors the Cycle 59 renderer:
# own session-state keys; earlier code NOT refactored.
# ============================================================================
_C67_SIG_STATE_KEY = "cycle67_signals_latest_v1"
_C67_SIG_AGE_KEY = "cycle67_candle_age_txt"
_C67_SIG_DIAG_KEY = "cycle67_signals_diag_v1"
_C67_SIG_FAIL_KEY = "cycle67_signals_fail_v1"


def _evaluate_c67_window(state, hour_utc, day=None):
    """Evaluate the 32 Cycle 67 (C67-04) equations for one entry window.

    Calls core.cycle67_best directly (not the signal router) so the result
    is always the C67 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle67_best import evaluate_cycle67_signals, select_cycle67_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C67_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C67_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle67_signals(frames, check_label)
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle67_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle67", payload)
        try:
            state[_C67_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c67_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C67 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C67_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c67_mark_fail(window_utc, state):
    """Record a failed C67 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C67_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C67_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle67_signals_table(st, state):
    """Cycle 67 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C67 entry window <= now (hours 1/6/16/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle67_best import CYCLE67_CHECK_HOURS as _C67_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C67_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C67_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c67_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 67 signals..."):
                new_payload = _evaluate_c67_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c67_mark_fail(latest_win, state)
            else:
                _c67_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 67 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 67 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C67_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 67 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle67", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C67_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 67 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C67_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 67 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 67 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C67_SIG_STATE_KEY) if isinstance(state.get(_C67_SIG_STATE_KEY), dict) else None


def render_cycle67_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 67 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle67_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 67 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 67 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle67_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle67")
            st.download_button(
                label="\U0001F4E5 Download Cycle 67 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle67_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return



# ============================================================================
# Cycle 78 (C78-34, July-only) signals table.
# C78-34 = the C66-08 entry engine FROZEN plus the
# Program-3 X30 at-entry stop-tightening layer
# (ER15(16) <= 0.20 & r1(1) >= 0 -> SL x0.90).
# Promoted by Muse's decision 2026-10-21 (15/16,
# fails only check 8, which C66-08 itself fails;
# LCT middle PASS). Mirrors the Cycle 66 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C78_SIG_STATE_KEY = "cycle78_signals_latest_v1"
_C78_SIG_AGE_KEY = "cycle78_candle_age_txt"
_C78_SIG_DIAG_KEY = "cycle78_signals_diag_v1"
_C78_SIG_FAIL_KEY = "cycle78_signals_fail_v1"


def _evaluate_c78_window(state, hour_utc, day=None):
    """Evaluate the 27 Cycle 78 (C78-34) equations for one entry window.

    Calls core.cycle78_best directly (not the signal router) so the result
    is always the C78 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle78_best import evaluate_cycle78_signals, select_cycle78_entries
    from core.cycle78_best import fetch_cycle78_m15_frames as _fetch_c78_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C78_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C78_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle78_signals(frames, check_label,
                                           m15_frames=_fetch_c78_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle78_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle78", payload)
        try:
            state[_C78_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c78_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C78 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C78_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c78_mark_fail(window_utc, state):
    """Record a failed C78 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C78_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C78_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle78_signals_table(st, state):
    """Cycle 78 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C78 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle78_best import CYCLE78_CHECK_HOURS as _C78_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C78_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C78_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c78_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 78 signals..."):
                new_payload = _evaluate_c78_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c78_mark_fail(latest_win, state)
            else:
                _c78_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 78 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 78 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C78_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 78 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle78", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C78_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 78 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C78_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 78 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 78 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C78_SIG_STATE_KEY) if isinstance(state.get(_C78_SIG_STATE_KEY), dict) else None


def render_cycle78_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 78 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle78_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 78 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 78 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle78_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle78")
            st.download_button(
                label="\U0001F4E5 Download Cycle 78 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle78_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 85 (C85-23, February-only) signals table.
# C85-23 = the C56-15 entry engine FROZEN minus
# 4 FB legs, plus TP x1.75 on surviving FB trades.
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle PASS P 90.42% / p5 40.14%). Mirrors the Cycle 85 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C85_SIG_STATE_KEY = "cycle85_signals_latest_v1"
_C85_SIG_AGE_KEY = "cycle85_candle_age_txt"
_C85_SIG_DIAG_KEY = "cycle85_signals_diag_v1"
_C85_SIG_FAIL_KEY = "cycle85_signals_fail_v1"


def _evaluate_c85_window(state, hour_utc, day=None):
    """Evaluate the 18 Cycle 85 (C85-23) equations for one entry window.

    Calls core.cycle85_best directly (not the signal router) so the result
    is always the C85 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle85_best import evaluate_cycle85_signals, select_cycle85_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C85_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C85_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle85_signals(frames, check_label)
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle85_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle85", payload)
        try:
            state[_C85_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c85_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C85 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C85_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c85_mark_fail(window_utc, state):
    """Record a failed C85 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C85_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C85_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle85_signals_table(st, state):
    """Cycle 85 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C85 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle85_best import CYCLE85_CHECK_HOURS as _C85_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C85_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C85_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c85_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 85 signals..."):
                new_payload = _evaluate_c85_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c85_mark_fail(latest_win, state)
            else:
                _c85_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 85 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 85 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C85_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 85 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle85", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C85_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 85 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C85_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 85 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 85 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C85_SIG_STATE_KEY) if isinstance(state.get(_C85_SIG_STATE_KEY), dict) else None


def render_cycle85_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 85 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle85_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 85 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 85 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle85_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle85")
            st.download_button(
                label="\U0001F4E5 Download Cycle 85 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle85_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 86 (C86-24, March-only) signals table.
# C86-24 = the C62-10 entry engine FROZEN minus
# FB_USDCAD_h16_1, plus the M08 Reject15 rerank
# in top-3 and TP x0.95 on FB trades.
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle PASS P 87.34% / p5 35.38%). Mirrors the Cycle 86 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C86_SIG_STATE_KEY = "cycle86_signals_latest_v1"
_C86_SIG_AGE_KEY = "cycle86_candle_age_txt"
_C86_SIG_DIAG_KEY = "cycle86_signals_diag_v1"
_C86_SIG_FAIL_KEY = "cycle86_signals_fail_v1"


def _evaluate_c86_window(state, hour_utc, day=None):
    """Evaluate the 28 Cycle 86 (C86-24) equations for one entry window.

    Calls core.cycle86_best directly (not the signal router) so the result
    is always the C86 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle86_best import evaluate_cycle86_signals, select_cycle86_entries
    from core.cycle86_best import fetch_cycle86_m15_frames as _fetch_c86_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C86_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C86_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle86_signals(frames, check_label,
                                           m15_frames=_fetch_c86_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle86_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle86", payload)
        try:
            state[_C86_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c86_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C86 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C86_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c86_mark_fail(window_utc, state):
    """Record a failed C86 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C86_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C86_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle86_signals_table(st, state):
    """Cycle 86 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C86 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle86_best import CYCLE86_CHECK_HOURS as _C86_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C86_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C86_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c86_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 86 signals..."):
                new_payload = _evaluate_c86_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c86_mark_fail(latest_win, state)
            else:
                _c86_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 86 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 86 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C86_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 86 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle86", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C86_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 86 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C86_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 86 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 86 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C86_SIG_STATE_KEY) if isinstance(state.get(_C86_SIG_STATE_KEY), dict) else None


def render_cycle86_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 86 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle86_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 86 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 86 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle86_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle86")
            st.download_button(
                label="\U0001F4E5 Download Cycle 86 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle86_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 87 (C87-24, April-only) signals table.
# C87-24 = the C63-04 entry engine FROZEN with 3
# FB legs banned, plus the M18 common-range
# rerank in top-3.
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle PASS P 92.44% / p5 65.55%). Mirrors the Cycle 87 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C87_SIG_STATE_KEY = "cycle87_signals_latest_v1"
_C87_SIG_AGE_KEY = "cycle87_candle_age_txt"
_C87_SIG_DIAG_KEY = "cycle87_signals_diag_v1"
_C87_SIG_FAIL_KEY = "cycle87_signals_fail_v1"


def _evaluate_c87_window(state, hour_utc, day=None):
    """Evaluate the 39 Cycle 87 (C87-24) equations for one entry window.

    Calls core.cycle87_best directly (not the signal router) so the result
    is always the C87 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle87_best import evaluate_cycle87_signals, select_cycle87_entries
    from core.cycle87_best import fetch_cycle87_m15_frames as _fetch_c87_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C87_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C87_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle87_signals(frames, check_label,
                                           m15_frames=_fetch_c87_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle87_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle87", payload)
        try:
            state[_C87_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c87_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C87 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C87_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c87_mark_fail(window_utc, state):
    """Record a failed C87 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C87_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C87_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle87_signals_table(st, state):
    """Cycle 87 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C87 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle87_best import CYCLE87_CHECK_HOURS as _C87_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C87_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C87_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c87_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 87 signals..."):
                new_payload = _evaluate_c87_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c87_mark_fail(latest_win, state)
            else:
                _c87_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 87 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 87 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C87_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 87 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle87", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C87_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 87 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C87_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 87 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 87 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C87_SIG_STATE_KEY) if isinstance(state.get(_C87_SIG_STATE_KEY), dict) else None


def render_cycle87_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 87 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle87_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 87 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 87 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle87_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle87")
            st.download_button(
                label="\U0001F4E5 Download Cycle 87 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle87_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 87B (BRIEF21 C20a IMPROVED, April BEST) signals table.
# Priority: 1st = this system (C87-24 + C12 score-gated dual-pick
# + C16 re-entry via the walk ledger); 2nd (only when 1st is
# silent at a check) = old Cycle 87 (C87-24) via the COMBINED
# panel. Validated BRIEF21: DISC n710 net +6033.02 leftover
# 84.47; AUDIT n187 net +1971.36 leftover 79.06; app replay
# EXACT 2026-10-26 (FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md).
# ============================================================================
_C87B_SIG_STATE_KEY = "cycle87b_signals_latest_v1"
_C87B_SIG_AGE_KEY = "cycle87b_candle_age_txt"
_C87B_SIG_DIAG_KEY = "cycle87b_signals_diag_v1"
_C87B_SIG_FAIL_KEY = "cycle87b_signals_fail_v1"


def _evaluate_c87b_window(state, hour_utc, day=None):
    """Evaluate the 39 Cycle 87B (C20a) equations for one entry window.

    Calls core.cycle87b_best directly (not the signal router) so the result
    is always the C87B system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle87b_best import evaluate_cycle87b_signals, select_cycle87b_entries
    from core.cycle87b_best import panel_entries
    from core.cycle87b_best import fetch_cycle87b_m15_frames as _fetch_c87b_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C87B_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C87B_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle87b_signals(frames, check_label,
                                           m15_frames=_fetch_c87b_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = panel_entries(frames, check_label,
                                    m15_frames=_fetch_c87b_m15(state),
                                    open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle87b", payload)
        try:
            state[_C87B_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c87b_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C87B window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C87B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c87b_mark_fail(window_utc, state):
    """Record a failed C87B evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C87B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C87B_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle87b_signals_table(st, state):
    """Cycle 87B signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C87B entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle87b_best import CYCLE87B_CHECK_HOURS as _C87B_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C87B_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C87B_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c87b_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 87B signals..."):
                new_payload = _evaluate_c87b_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c87b_mark_fail(latest_win, state)
            else:
                _c87b_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 87B signals \u2014 April IMPROVED system (BRIEF21 C20a)")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 87B entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C87B_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 87B evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle87b", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C87B_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 87B equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C87B_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 87B equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 87B equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C87B_SIG_STATE_KEY) if isinstance(state.get(_C87B_SIG_STATE_KEY), dict) else None


def render_cycle87b_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 87B signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle87b_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 87B CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 87B signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle87b_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle87B")
            st.download_button(
                label="\U0001F4E5 Download Cycle 87B signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle87b_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 88 (C88-03, May-only) signals table.
# C88-03 = the C64-09 entry engine FROZEN minus
# the entire FB layer (all 9 FB legs).
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle+strict PASS P 100.00% / p5 84.43%). Mirrors the Cycle 88 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C88_SIG_STATE_KEY = "cycle88_signals_latest_v1"
_C88_SIG_AGE_KEY = "cycle88_candle_age_txt"
_C88_SIG_DIAG_KEY = "cycle88_signals_diag_v1"
_C88_SIG_FAIL_KEY = "cycle88_signals_fail_v1"


def _evaluate_c88_window(state, hour_utc, day=None):
    """Evaluate the 21 Cycle 88 (C88-03) equations for one entry window.

    Calls core.cycle88_best directly (not the signal router) so the result
    is always the C88 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle88_best import evaluate_cycle88_signals, select_cycle88_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C88_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C88_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle88_signals(frames, check_label)
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle88_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle88", payload)
        try:
            state[_C88_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c88_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C88 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C88_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c88_mark_fail(window_utc, state):
    """Record a failed C88 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C88_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C88_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle88_signals_table(st, state):
    """Cycle 88 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C88 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle88_best import CYCLE88_CHECK_HOURS as _C88_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C88_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C88_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c88_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 88 signals..."):
                new_payload = _evaluate_c88_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c88_mark_fail(latest_win, state)
            else:
                _c88_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 88 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 88 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C88_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 88 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle88", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C88_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 88 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C88_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 88 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 88 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C88_SIG_STATE_KEY) if isinstance(state.get(_C88_SIG_STATE_KEY), dict) else None


def render_cycle88_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 88 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle88_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 88 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 88 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle88_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle88")
            st.download_button(
                label="\U0001F4E5 Download Cycle 88 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle88_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 89 (C89-21, June-only) signals table.
# C89-21 = the C65-01 entry engine FROZEN minus
# FB_AUDJPY_h18_0, plus the FBGATE veto on h18
# bench picks and TP x1.25 on the REV_lr2 legs.
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle+strict PASS P 99.91% / p5 52.13%). Mirrors the Cycle 89 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C89_SIG_STATE_KEY = "cycle89_signals_latest_v1"
_C89_SIG_AGE_KEY = "cycle89_candle_age_txt"
_C89_SIG_DIAG_KEY = "cycle89_signals_diag_v1"
_C89_SIG_FAIL_KEY = "cycle89_signals_fail_v1"


def _evaluate_c89_window(state, hour_utc, day=None):
    """Evaluate the 29 Cycle 89 (C89-21) equations for one entry window.

    Calls core.cycle89_best directly (not the signal router) so the result
    is always the C89 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle89_best import evaluate_cycle89_signals, select_cycle89_entries
    from core.cycle89_best import fetch_cycle89_m15_frames as _fetch_c89_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C89_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C89_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle89_signals(frames, check_label,
                                           m15_frames=_fetch_c89_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle89_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle89", payload)
        try:
            state[_C89_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c89_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C89 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C89_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c89_mark_fail(window_utc, state):
    """Record a failed C89 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C89_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C89_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle89_signals_table(st, state):
    """Cycle 89 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C89 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle89_best import CYCLE89_CHECK_HOURS as _C89_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C89_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C89_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c89_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 89 signals..."):
                new_payload = _evaluate_c89_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c89_mark_fail(latest_win, state)
            else:
                _c89_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 89 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 89 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C89_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 89 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle89", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C89_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 89 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C89_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 89 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 89 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C89_SIG_STATE_KEY) if isinstance(state.get(_C89_SIG_STATE_KEY), dict) else None


def render_cycle89_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 89 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle89_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 89 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 89 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle89_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle89")
            st.download_button(
                label="\U0001F4E5 Download Cycle 89 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle89_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 91 (C91-15, September-only) signals table.
# C91-15 = the C59-18 entry engine FROZEN minus
# 3 hour-1 FB legs, plus the X30B at-entry
# overlay (ER15(16) <= 0.25 & r1(1) >= 0 ->
# SL x0.85).
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle PASS P 80.28% / p5 24.63%). Mirrors the Cycle 91 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C91_SIG_STATE_KEY = "cycle91_signals_latest_v1"
_C91_SIG_AGE_KEY = "cycle91_candle_age_txt"
_C91_SIG_DIAG_KEY = "cycle91_signals_diag_v1"
_C91_SIG_FAIL_KEY = "cycle91_signals_fail_v1"


def _evaluate_c91_window(state, hour_utc, day=None):
    """Evaluate the 21 Cycle 91 (C91-15) equations for one entry window.

    Calls core.cycle91_best directly (not the signal router) so the result
    is always the C91 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle91_best import evaluate_cycle91_signals, select_cycle91_entries
    from core.cycle91_best import fetch_cycle91_m15_frames as _fetch_c91_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C91_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C91_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle91_signals(frames, check_label,
                                           m15_frames=_fetch_c91_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle91_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle91", payload)
        try:
            state[_C91_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c91_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C91 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C91_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c91_mark_fail(window_utc, state):
    """Record a failed C91 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C91_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C91_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle91_signals_table(st, state):
    """Cycle 91 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C91 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle91_best import CYCLE91_CHECK_HOURS as _C91_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C91_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C91_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c91_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 91 signals..."):
                new_payload = _evaluate_c91_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c91_mark_fail(latest_win, state)
            else:
                _c91_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 91 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 91 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C91_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 91 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle91", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C91_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 91 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C91_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 91 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 91 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C91_SIG_STATE_KEY) if isinstance(state.get(_C91_SIG_STATE_KEY), dict) else None


def render_cycle91_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 91 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle91_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 91 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 91 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle91_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle91")
            st.download_button(
                label="\U0001F4E5 Download Cycle 91 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle91_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 287 (C287, September SECOND-BEST) signals table.
# C287 = the C91-15 walk VERBATIM, kept only where the
# BRIEF18 depth-3 confirmation stack passes (M15 hammer
# aligned BUY & M15 pin-bar aligned BUY & RSI-reversal).
# Discovery n12 / leftover 100.00; audit n2 / 100.00 --
# very thin samples. Integrated 2026-10-25 under the
# user's waiver of the chain-floor and DSR terms.
# September's best/default system remains Cycle 91
# (C91-15); this panel is the selectable second-best
# alternative only.
# ============================================================================
_C287_SIG_STATE_KEY = "cycle287_signals_latest_v1"
_C287_SIG_AGE_KEY = "cycle287_candle_age_txt"
_C287_SIG_DIAG_KEY = "cycle287_signals_diag_v1"
_C287_SIG_FAIL_KEY = "cycle287_signals_fail_v1"


def _evaluate_c287_window(state, hour_utc, day=None):
    """Evaluate the 21 Cycle 287 (C287) equations for one entry window.

    Calls core.cycle287_best directly (not the signal router) so the result
    is always the C287 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle287_best import evaluate_cycle287_signals, select_cycle287_entries
    from core.cycle287_best import fetch_cycle287_m15_frames as _fetch_c287_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C287_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C287_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle287_signals(frames, check_label,
                                           m15_frames=_fetch_c287_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle287_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle287", payload)
        try:
            state[_C287_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c287_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C287 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C287_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c287_mark_fail(window_utc, state):
    """Record a failed C287 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C287_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C287_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle287_signals_table(st, state):
    """Cycle 287 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C287 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle287_best import CYCLE287_CHECK_HOURS as _C287_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C287_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C287_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c287_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 287 signals..."):
                new_payload = _evaluate_c287_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c287_mark_fail(latest_win, state)
            else:
                _c287_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 287 signals \u2014 September SECOND-BEST system")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 287 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C287_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 287 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle287", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C287_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 287 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C287_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 287 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 287 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C287_SIG_STATE_KEY) if isinstance(state.get(_C287_SIG_STATE_KEY), dict) else None


def render_cycle287_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 287 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle287_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 287 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 287 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle287_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle287")
            st.download_button(
                label="\U0001F4E5 Download Cycle 287 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle287_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 92 (C92-24, October-only) signals table.
# C92-24 = the C69-07 entry engine FROZEN minus
# 4 FB legs, plus 7 screened fresh legs at
# fallback-tier scores 512-506.
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle+strict PASS P 100.00% / p5 70.20%). Mirrors the Cycle 92 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# Cycle 155 (2026-10-23): the October selection also returns
# the VALIDATED dual-pick second entry (non-FB, fewer than 3
# open) when it fires -- see core/cycle92_best.py and
# FIX_NOTES_20261023_CYCLE155_OCTOBER_DUALPICK.md.
# ============================================================================
_C92_SIG_STATE_KEY = "cycle92_signals_latest_v1"
_C92_SIG_AGE_KEY = "cycle92_candle_age_txt"
_C92_SIG_DIAG_KEY = "cycle92_signals_diag_v1"
_C92_SIG_FAIL_KEY = "cycle92_signals_fail_v1"


def _evaluate_c92_window(state, hour_utc, day=None):
    """Evaluate the 36 Cycle 92 (C92-24) equations for one entry window.

    Calls core.cycle92_best directly (not the signal router) so the result
    is always the C92 system regardless of the active mode. Primary entry
    per check (top-1 by score) plus the Cycle 155 dual-pick second entry
    when it fires. Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle92_best import evaluate_cycle92_signals, select_cycle92_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C92_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C92_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle92_signals(frames, check_label)
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle92_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle92", payload)
        try:
            state[_C92_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c92_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C92 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C92_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c92_mark_fail(window_utc, state):
    """Record a failed C92 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C92_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C92_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle92_signals_table(st, state):
    """Cycle 92 signals table: backfilled + persisted, primary entry/check
    plus the Cycle 155 dual-pick second entry when it fires.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C92 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle92_best import CYCLE92_CHECK_HOURS as _C92_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C92_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C92_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c92_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 155 dual-pick signals..."):
                new_payload = _evaluate_c92_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c92_mark_fail(latest_win, state)
            else:
                _c92_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 155 dual-pick signals (October BEST, C92-24 base)")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 155 dual-pick entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C92_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 155 dual-pick evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle92", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C92_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 155/C92-24 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C92_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 155/C92-24 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 155/C92-24 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C92_SIG_STATE_KEY) if isinstance(state.get(_C92_SIG_STATE_KEY), dict) else None


def render_cycle92_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 92 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle92_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 92 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 92 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle92_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle92")
            st.download_button(
                label="\U0001F4E5 Download Cycle 92 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle92_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 93 (C93-24, November-only) signals table.
# C93-24 = the C70-07 entry engine FROZEN minus
# 8 FB legs and the CYB EURNZD h9 leg, plus the
# FBGATE veto on the surviving FB leg.
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle PASS P 83.42% / p5 46.18%). Mirrors the Cycle 93 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C93_SIG_STATE_KEY = "cycle93_signals_latest_v1"
_C93_SIG_AGE_KEY = "cycle93_candle_age_txt"
_C93_SIG_DIAG_KEY = "cycle93_signals_diag_v1"
_C93_SIG_FAIL_KEY = "cycle93_signals_fail_v1"


def _evaluate_c93_window(state, hour_utc, day=None):
    """Evaluate the 15 Cycle 93 (C93-24) equations for one entry window.

    Calls core.cycle93_best directly (not the signal router) so the result
    is always the C93 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle93_best import evaluate_cycle93_signals, select_cycle93_entries
    from core.cycle93_best import fetch_cycle93_m15_frames as _fetch_c93_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C93_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C93_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle93_signals(frames, check_label,
                                           m15_frames=_fetch_c93_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle93_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle93", payload)
        try:
            state[_C93_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c93_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C93 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C93_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c93_mark_fail(window_utc, state):
    """Record a failed C93 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C93_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C93_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle93_signals_table(st, state):
    """Cycle 93 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C93 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle93_best import CYCLE93_CHECK_HOURS as _C93_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C93_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C93_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c93_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 93 signals..."):
                new_payload = _evaluate_c93_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c93_mark_fail(latest_win, state)
            else:
                _c93_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 93 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 93 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C93_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 93 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle93", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C93_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 93 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C93_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 93 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 93 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C93_SIG_STATE_KEY) if isinstance(state.get(_C93_SIG_STATE_KEY), dict) else None


def render_cycle93_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 93 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle93_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 93 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 93 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle93_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle93")
            st.download_button(
                label="\U0001F4E5 Download Cycle 93 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle93_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 93B (BRIEF21 C20a IMPROVED, November BEST) signals table.
# Priority: 1st = this system (C93-24 + C06 vol veto + C16
# re-entry via the walk ledger); 2nd (only when 1st is silent
# at a check) = old Cycle 93 (C93-24) via the COMBINED panel.
# Validated BRIEF21: DISC n436 net +5128.59 leftover 69.12;
# AUDIT n100 net +678.37 leftover 46.39; app replay EXACT
# 2026-10-26 (FIX_NOTES_20261026_BRIEF21_APP_INTEGRATION.md).
# ============================================================================
_C93B_SIG_STATE_KEY = "cycle93b_signals_latest_v1"
_C93B_SIG_AGE_KEY = "cycle93b_candle_age_txt"
_C93B_SIG_DIAG_KEY = "cycle93b_signals_diag_v1"
_C93B_SIG_FAIL_KEY = "cycle93b_signals_fail_v1"


def _evaluate_c93b_window(state, hour_utc, day=None):
    """Evaluate the 15 Cycle 93B (C20a) equations for one entry window.

    Calls core.cycle93b_best directly (not the signal router) so the result
    is always the C93B system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle93b_best import evaluate_cycle93b_signals
    from core.cycle93b_best import panel_entries
    from core.cycle93b_best import fetch_cycle93b_m15_frames as _fetch_c93b_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C93B_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C93B_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle93b_signals(frames, check_label,
                                           m15_frames=_fetch_c93b_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = panel_entries(frames, check_label,
                                    m15_frames=_fetch_c93b_m15(state),
                                    open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle93b", payload)
        try:
            state[_C93B_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c93b_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C93B window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C93B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c93b_mark_fail(window_utc, state):
    """Record a failed C93B evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C93B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C93B_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle93b_signals_table(st, state):
    """Cycle 93B signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C93B entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle93b_best import CYCLE93B_CHECK_HOURS as _C93B_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C93B_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C93B_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c93b_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 93B signals..."):
                new_payload = _evaluate_c93b_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c93b_mark_fail(latest_win, state)
            else:
                _c93b_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 93B signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 93B entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C93B_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 93B evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle93b", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C93B_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 93B equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C93B_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 93B equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 93B equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C93B_SIG_STATE_KEY) if isinstance(state.get(_C93B_SIG_STATE_KEY), dict) else None


def render_cycle93b_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 93B signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle93b_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 93B CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 93B signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle93b_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle93B")
            st.download_button(
                label="\U0001F4E5 Download Cycle 93B signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle93b_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 94 (C94-23, December-only) signals table.
# C94-23 = the C71-04 entry engine FROZEN
# verbatim, plus the FB-pick gate (ATR14
# percentile > 70 & M15 CLV < 0.45 -> veto).
# Promoted by Muse's decision 2026-10-21 (Program 4;
# LCT middle PASS P 94.14% / p5 31.54%). Mirrors the Cycle 94 renderer:
# own session-state keys; the working earlier cycle
# code is NOT refactored.
# ============================================================================
_C94_SIG_STATE_KEY = "cycle94_signals_latest_v1"
_C94_SIG_AGE_KEY = "cycle94_candle_age_txt"
_C94_SIG_DIAG_KEY = "cycle94_signals_diag_v1"
_C94_SIG_FAIL_KEY = "cycle94_signals_fail_v1"


def _evaluate_c94_window(state, hour_utc, day=None):
    """Evaluate the 34 Cycle 94 (C94-23) equations for one entry window.

    Calls core.cycle94_best directly (not the signal router) so the result
    is always the C94 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle94_best import evaluate_cycle94_signals, select_cycle94_entries
    from core.cycle94_best import fetch_cycle94_m15_frames as _fetch_c94_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C94_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C94_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle94_signals(frames, check_label,
                                           m15_frames=_fetch_c94_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle94_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle94", payload)
        try:
            state[_C94_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c94_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C94 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C94_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c94_mark_fail(window_utc, state):
    """Record a failed C94 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C94_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C94_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle94_signals_table(st, state):
    """Cycle 94 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C94 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle94_best import CYCLE94_CHECK_HOURS as _C94_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C94_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C94_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c94_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 94 signals..."):
                new_payload = _evaluate_c94_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c94_mark_fail(latest_win, state)
            else:
                _c94_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 94 signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 94 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C94_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 94 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle94", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C94_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 94 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C94_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 94 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 94 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C94_SIG_STATE_KEY) if isinstance(state.get(_C94_SIG_STATE_KEY), dict) else None


def render_cycle94_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 94 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle94_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 94 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 94 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle94_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle94")
            st.download_button(
                label="\U0001F4E5 Download Cycle 94 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle94_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 274 (C274, December SECOND-BEST) signals table.
# C274 = the C94-23 walk VERBATIM (FB gate included),
# kept only where the BRIEF18 depth-10 confirmation
# stack passes. Discovery n31 / leftover 100.00; audit
# n5 / 100.00. Integrated 2026-10-25 under the user's
# waiver of the chain-floor and DSR terms. December's
# best/default system remains Cycle 94 (C94-23); this
# panel is the selectable second-best alternative only.
# ============================================================================
_C274_SIG_STATE_KEY = "cycle274_signals_latest_v1"
_C274_SIG_AGE_KEY = "cycle274_candle_age_txt"
_C274_SIG_DIAG_KEY = "cycle274_signals_diag_v1"
_C274_SIG_FAIL_KEY = "cycle274_signals_fail_v1"


def _evaluate_c274_window(state, hour_utc, day=None):
    """Evaluate the 34 Cycle 274 (C274) equations for one entry window.

    Calls core.cycle274_best directly (not the signal router) so the result
    is always the C274 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle274_best import evaluate_cycle274_signals, select_cycle274_entries
    from core.cycle274_best import fetch_cycle274_m15_frames as _fetch_c274_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C274_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C274_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle274_signals(frames, check_label,
                                           m15_frames=_fetch_c274_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle274_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle274", payload)
        try:
            state[_C274_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c274_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C274 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C274_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c274_mark_fail(window_utc, state):
    """Record a failed C274 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C274_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C274_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle274_signals_table(st, state):
    """Cycle 274 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C274 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle274_best import CYCLE274_CHECK_HOURS as _C274_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C274_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C274_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c274_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 274 signals..."):
                new_payload = _evaluate_c274_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c274_mark_fail(latest_win, state)
            else:
                _c274_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 274 signals \u2014 December SECOND-BEST system")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 274 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C274_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 274 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle274", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C274_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 274 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C274_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 274 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 274 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C274_SIG_STATE_KEY) if isinstance(state.get(_C274_SIG_STATE_KEY), dict) else None


def render_cycle274_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 274 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle274_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 274 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 274 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle274_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle274")
            st.download_button(
                label="\U0001F4E5 Download Cycle 274 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle274_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 94B (BRIEF21 C20a IMPROVED, December BEST) signals table.
# Priority: 1st = this system (C94-23 + C06 vol veto + C16
# re-entry via the walk ledger); 2nd (only when 1st is silent
# at a check) = old Cycle 94 (C94-23) via the COMBINED panel.
# Cycle 274 stays selectable standalone. Validated BRIEF21:
# DISC n650 net +4479.75 leftover 66.20; AUDIT n157 net
# +1135.57 leftover 75.39; app replay EXACT 2026-10-26.
# ============================================================================
_C94B_SIG_STATE_KEY = "cycle94b_signals_latest_v1"
_C94B_SIG_AGE_KEY = "cycle94b_candle_age_txt"
_C94B_SIG_DIAG_KEY = "cycle94b_signals_diag_v1"
_C94B_SIG_FAIL_KEY = "cycle94b_signals_fail_v1"


def _evaluate_c94b_window(state, hour_utc, day=None):
    """Evaluate the 34 Cycle 94B (C20a) equations for one entry window.

    Calls core.cycle94b_best directly (not the signal router) so the result
    is always the C94B system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle94b_best import evaluate_cycle94b_signals
    from core.cycle94b_best import panel_entries
    from core.cycle94b_best import fetch_cycle94b_m15_frames as _fetch_c94b_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C94B_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C94B_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle94b_signals(frames, check_label,
                                           m15_frames=_fetch_c94b_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = panel_entries(frames, check_label,
                                    m15_frames=_fetch_c94b_m15(state),
                                    open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle94b", payload)
        try:
            state[_C94B_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c94b_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C94B window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C94B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c94b_mark_fail(window_utc, state):
    """Record a failed C94B evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C94B_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C94B_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle94b_signals_table(st, state):
    """Cycle 94B signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C94B entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle94b_best import CYCLE94B_CHECK_HOURS as _C94B_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C94B_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C94B_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c94b_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 94B signals..."):
                new_payload = _evaluate_c94b_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c94b_mark_fail(latest_win, state)
            else:
                _c94b_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 94B signals")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 94B entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C94B_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 94B evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle94b", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C94B_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 94B equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C94B_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 94B equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 94B equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C94B_SIG_STATE_KEY) if isinstance(state.get(_C94B_SIG_STATE_KEY), dict) else None


def render_cycle94b_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 94B signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle94b_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 94B CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 94B signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle94b_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle94B")
            st.download_button(
                label="\U0001F4E5 Download Cycle 94B signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle94b_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


# Cycle 274 (C274, December SECOND-BEST) signals table.
# C274 = the C20a walk VERBATIM (FB gate included),
# kept only where the BRIEF18 depth-10 confirmation
# stack passes. Discovery n31 / leftover 100.00; audit
# n5 / 100.00. Integrated 2026-10-25 under the user's
# waiver of the chain-floor and DSR terms. December's
# best/default system remains Cycle 94B (C20a); this
# panel is the selectable second-best alternative only.
# ============================================================================
_C274_SIG_STATE_KEY = "cycle274_signals_latest_v1"
_C274_SIG_AGE_KEY = "cycle274_candle_age_txt"
_C274_SIG_DIAG_KEY = "cycle274_signals_diag_v1"
_C274_SIG_FAIL_KEY = "cycle274_signals_fail_v1"


def _evaluate_c274_window(state, hour_utc, day=None):
    """Evaluate the 34 Cycle 274 (C274) equations for one entry window.

    Calls core.cycle274_best directly (not the signal router) so the result
    is always the C274 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle274_best import evaluate_cycle274_signals, select_cycle274_entries
    from core.cycle274_best import fetch_cycle274_m15_frames as _fetch_c274_m15
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C274_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C274_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            sig = evaluate_cycle274_signals(frames, check_label,
                                           m15_frames=_fetch_c274_m15(state))
            _require_evaluator_status(sig)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            sig = _pd.DataFrame()
        try:
            if diag.get("evaluation_error"):
                raise ValueError("evaluation_incomplete")
            entries = select_cycle274_entries(sig, open_symbols=())
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries = _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            payload["ranking"] = _c22_build_check_ranking(sig, entries, frames, need)
        except Exception:
            pass
        _record_eval_history("cycle274", payload)
        try:
            state[_C274_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c274_recent_fail(window_utc, state, cool_minutes=0.25):
    """True if this C274 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C274_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _c274_mark_fail(window_utc, state):
    """Record a failed C274 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C274_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C274_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle274_signals_table(st, state):
    """Cycle 274 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors the C27 renderer: on EVERY render, computes the
    latest C274 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for NO TIME LIMIT after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle274_best import CYCLE274_CHECK_HOURS as _C274_CHECK_HOURS
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C274_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        latest_win = _latest_entry_window_utc(now_utc, hours=_C274_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _c274_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 274 signals..."):
                new_payload = _evaluate_c274_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _c274_mark_fail(latest_win, state)
            else:
                _c274_mark_fail(latest_win, state)

        st.markdown("### \U0001F3AF Cycle 274 signals \u2014 December SECOND-BEST system")
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 274 entry window -- signals will "
                    "appear here and stay visible until a newer window arrives.")
            try:
                diag = state.get(_C274_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"\u26a0\ufe0f Last Cycle 274 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        # UNLIMITED VISIBILITY (user order 2026-10-21): the former
        # 2-hour expiry is removed -- the latest stored window (its
        # check time + entries) stays visible until a newer window
        # replaces it. age_min now only feeds the header age text.
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                "cycle274", live_tag),
            unsafe_allow_html=True,
        )
        st.caption(f"Check candles ready: {payload.get('n_evaluable', 0)}/20")
        disp = payload.get("signals")
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                _ql_items = [str(_v) for _v in disp["Quick look"].tolist()
                             if str(_v).strip()]
                if _ql_items:
                    st.markdown("### \U0001F4CC ENTRY: "
                                + " \u00b7 ".join(_ql_items))
                    st.write("")
                    st.write("")
            except Exception:
                pass
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            try:
                state[_C274_SIG_STATE_KEY + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
        _ranking = payload.get("ranking")
        _has_ranking = isinstance(_ranking, _pd.DataFrame) and not _ranking.empty
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            elif _has_ranking:
                # User order 2026-10-22 (round 2): bare text must NEVER
                # replace the table -- one status line, then the full
                # ranking of every evaluated symbol below.
                st.info("No Cycle 274 equations fired in this window \u2014 "
                        "every evaluated symbol is ranked in the table below.")
            else:
                _last_entry = state.get(_C274_SIG_STATE_KEY + ":last_entry")
                if (isinstance(_last_entry, dict)
                        and isinstance(_last_entry.get("signals"), _pd.DataFrame)
                        and not _last_entry["signals"].empty):
                    st.info("No Cycle 274 equations fired in this window \u2014 "
                            "showing the last entry (Window "
                            f"{_last_entry.get('window_mmt', '\u2014')} MMT):")
                    st.dataframe(_last_entry["signals"],
                                 use_container_width=True, hide_index=True)
                else:
                    st.info("No Cycle 274 equations fired in this window.")
        else:
            st.table(_entry_row_colors(disp))
        if _has_ranking:
            st.markdown("**All evaluated symbols \u2014 latest check ranking**")
            st.table(_entry_row_colors(_ranking))
        return payload
    except Exception:
        return state.get(_C274_SIG_STATE_KEY) if isinstance(state.get(_C274_SIG_STATE_KEY), dict) else None


def render_cycle274_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 274 signals."""
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"cycle274_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 274 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="\U0001F4E5 Download Cycle 274 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle274_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle274")
            st.download_button(
                label="\U0001F4E5 Download Cycle 274 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle274_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


def _auto_refresh_field3(st: Any, interval_ms: int = 30_000) -> None:
    """Rerun the Field 3 page every 30 s so the countdown and Cycle 22
    signals update without a manual reload.

    Preferred: ``streamlit_autorefresh`` (pinned in requirements.txt).
    Fallback: a ``<meta http-equiv="refresh">`` tag.

    Safe against fetch storms: the startup auto-load skips when a completed
    generation already exists (once per session), and the per-window Cycle 22
    evaluation is memoized by window key, so extra reruns are cheap.
    """
    try:
        from core.check_candle_runtime import check_refresh_interval_ms
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=min(interval_ms, check_refresh_interval_ms()),
                       limit=None, key="field3_c22_refresh")
    except Exception:
        st.markdown(
            '<meta http-equiv="refresh" content="30">',
            unsafe_allow_html=True,
        )



# ============================================================================
# COMBINED Best + Second-Best panels (2026-10-26, user order).
#
# Rule, exactly as ordered: at any check time, the month's BEST cycle
# has priority; the month's SECOND-BEST cycle is evaluated and its
# pick shown ONLY when the best cycle produces NO entry at that check
# time. The panels below implement the rule through
# core.signal_mode.evaluate_combined_entries for the two months that
# carry an in-app second-best module -- September (best Cycle 91
# C91-15, second best Cycle 287 C287) and December (best Cycle 94
# C94-23, second best Cycle 274 C274). Picks are visibly labelled
# "BEST" or "SECOND BEST". Every incumbent panel and default is
# unchanged; these combined panels are APPENDED at the end of
# _MONTH_PANEL_ORDER (the original 12 positions never shift).
# ============================================================================

COMBINED_RULE_TEXT = (
    "12-system rebuild (2026-10-27): exactly 12 month systems, one "
    "per month, in month order. At every check time, each month's "
    "BEST cycle runs first and has priority; the SECOND-BEST cycle "
    "is evaluated and shown ONLY when the Best cycle has NO entry "
    "at that check time. Map: January -- 1st Cycle 60B (BRIEF23 "
    "C20_STACK), 2nd old Cycle 60 (C60-03). February -- Cycle 85 "
    "(C85-23) best-only. March -- Cycle 86 (C86-24) best-only. "
    "April -- 1st Cycle 87B (BRIEF21 C20a), 2nd old Cycle 87 "
    "(C87-24). May -- Cycle 88 (C88-03) best-only. June -- Cycle "
    "89 (C89-21) best-only. July -- Cycle 78 (C78-34) best-only. "
    "August -- Cycle 67 (C67-04) best-only. September -- 1st Cycle "
    "91 (C91-15), 2nd Cycle 287. October -- Cycle 92 with the C155 "
    "dual-pick, best-only. November -- 1st Cycle 93B (BRIEF21 "
    "C20a), 2nd old Cycle 93 (C93-24). December -- 1st Cycle 94B "
    "(BRIEF21 C20a), 2nd Cycle 274 (C274 stack). The NEW8 research "
    "improvements (Feb/Jun/Sep/Apr/May/Nov new bests, Aug/Oct new "
    "second bests) were NOT installed: their recorded picks sit on "
    "symbols this app does not carry (GBPAUD/GBPCAD/GBPNZD/"
    "DOLLARIDX), so they cannot be replayed exactly in-app -- "
    "blocked with proof in the 2026-10-27 build record; March's "
    "NEW8 second-best layer merged to zero trades in research "
    "itself. February H485 and July C407 remain research-only "
    "(blocked with proof 2026-10-25). Position sizing: Best N "
    "divided by 3 stays active for every month."
)

_COMBINED_CFG = {
    1: {
        "sysid": "cycle60bcombined",
        "month_name": "January",
        "best_id": "cycle60b",
        "best_label": "Cycle 60B (BRIEF23 C20_STACK IMPROVED)",
        "second_id": "cycle60",
        "second_label": "Cycle 60 (C60-03, old system)",
        "hours_mod": "core.cycle60b_best",
        "hours_attr": "CYCLE60B_CHECK_HOURS",
        "state_key": "combined_jan_signals_latest_v1",
        "age_key": "combined_jan_candle_age_txt",
        "diag_key": "combined_jan_signals_diag_v1",
        "fail_key": "combined_jan_signals_fail_v1",
        "dl_base": "january_combined_signals",
        "sheet": "JanCombined",
    },
    4: {
        "sysid": "cycle87bcombined",
        "month_name": "April",
        "best_id": "cycle87b",
        "best_label": "Cycle 87B (BRIEF21 C20a IMPROVED)",
        "second_id": "cycle87",
        "second_label": "Cycle 87 (C87-24, old system)",
        "hours_mod": "core.cycle87b_best",
        "hours_attr": "CYCLE87B_CHECK_HOURS",
        "state_key": "combined_apr_signals_latest_v1",
        "age_key": "combined_apr_candle_age_txt",
        "diag_key": "combined_apr_signals_diag_v1",
        "fail_key": "combined_apr_signals_fail_v1",
        "dl_base": "april_combined_signals",
        "sheet": "AprCombined",
    },
    9: {
        "sysid": "cycle91combined",
        "month_name": "September",
        "best_id": "cycle91",
        "best_label": "Cycle 91 (C91-15)",
        "second_id": "cycle287",
        "second_label": "Cycle 287 (C287)",
        "hours_mod": "core.cycle91_best",
        "hours_attr": "CYCLE91_CHECK_HOURS",
        "state_key": "combined_sep_signals_latest_v1",
        "age_key": "combined_sep_candle_age_txt",
        "diag_key": "combined_sep_signals_diag_v1",
        "fail_key": "combined_sep_signals_fail_v1",
        "dl_base": "september_combined_signals",
        "sheet": "SepCombined",
    },
    11: {
        "sysid": "cycle93bcombined",
        "month_name": "November",
        "best_id": "cycle93b",
        "best_label": "Cycle 93B (BRIEF21 C20a IMPROVED)",
        "second_id": "cycle93",
        "second_label": "Cycle 93 (C93-24, old system)",
        "hours_mod": "core.cycle93b_best",
        "hours_attr": "CYCLE93B_CHECK_HOURS",
        "state_key": "combined_nov_signals_latest_v1",
        "age_key": "combined_nov_candle_age_txt",
        "diag_key": "combined_nov_signals_diag_v1",
        "fail_key": "combined_nov_signals_fail_v1",
        "dl_base": "november_combined_signals",
        "sheet": "NovCombined",
    },
    12: {
        "sysid": "cycle94combined",
        "month_name": "December",
        "best_id": "cycle94b",
        "best_label": "Cycle 94B (BRIEF21 C20a IMPROVED)",
        "second_id": "cycle274",
        "second_label": "Cycle 274 (C274 stack)",
        "hours_mod": "core.cycle94b_best",
        "hours_attr": "CYCLE94B_CHECK_HOURS",
        "state_key": "combined_dec_signals_latest_v1",
        "age_key": "combined_dec_candle_age_txt",
        "diag_key": "combined_dec_signals_diag_v1",
        "fail_key": "combined_dec_signals_fail_v1",
        "dl_base": "december_combined_signals",
        "sheet": "DecCombined",
    },
}

_COMBINED_CFG_BY_SYSID = {cfg["sysid"]: cfg for cfg in _COMBINED_CFG.values()}
_COMBINED_CFG_SYSIDS = frozenset(_COMBINED_CFG_BY_SYSID)


def _combined_check_hours(month):
    import importlib as _il
    cfg = _COMBINED_CFG[month]
    mod = _il.import_module(cfg["hours_mod"])
    return tuple(getattr(mod, cfg["hours_attr"]))


def _evaluate_combined_window(state, month, hour_utc, day=None):
    """Evaluate one combined (best-first) window for September/December.

    Runs core.signal_mode.evaluate_combined_entries: the BEST system
    is evaluated and selected first; the SECOND-BEST system is
    evaluated ONLY when the best selection is empty. Stores the
    payload (display signals tagged BEST / SECOND BEST) in session
    state; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.signal_mode import evaluate_combined_entries
    cfg = _COMBINED_CFG[month]
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[cfg["age_key"]] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[cfg["diag_key"]] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            _require_check_frames(frames, need)
            entries, source = evaluate_combined_entries(
                month, frames, check_label, open_symbols=())
            _require_evaluator_status(entries)
        except Exception as exc:
            diag = dict(diag or {})
            diag["evaluation_error"] = type(exc).__name__
            entries, source = _pd.DataFrame(), "BEST"
        source_label = "SECOND BEST" if source == "SECOND_BEST" else "BEST"
        source_system = cfg["second_id"] if source == "SECOND_BEST" else cfg["best_id"]
        try:
            if isinstance(entries, _pd.DataFrame) and len(entries):
                source_system = str(entries["source_system"].iloc[0])
        except Exception:
            pass
        disp = _c22_signals_to_display(entries)
        if isinstance(disp, _pd.DataFrame) and not disp.empty:
            disp = disp.copy()
            disp.insert(1, "Source", source_label)
            try:
                disp["Quick look"] = source_label + " \u00b7 " + disp["Quick look"].astype(str)
            except Exception:
                pass
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        if n_evaluable < len(_CYCLE22_PANEL_SYMBOLS) or diag.get("evaluation_error"):
            entries = _pd.DataFrame()
            if "disp" in locals():
                disp = _pd.DataFrame()
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "diag": diag,
            "signals": disp,
            "source": source,
            "source_label": source_label,
            "source_system": source_system,
        }
        payload["ranking"] = _c22_build_check_ranking(entries, entries, frames, need)
        _record_eval_history(cfg["sysid"], payload)
        try:
            state[cfg["state_key"]] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _combined_recent_fail(window_utc, state, month, cool_minutes=0.25):
    """True if this combined window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    cfg = _COMBINED_CFG[month]
    try:
        fails = state.get(cfg["fail_key"])
        if not isinstance(fails, dict):
            return False
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        ts = fails.get(key)
        if ts is None:
            return False
        failed_at = _pd.Timestamp(ts)
        now = _pd.Timestamp(_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        return (now - failed_at).total_seconds() < cool_minutes * 60
    except Exception:
        return False


def _combined_mark_fail(window_utc, state, month):
    """Record a failed combined evaluation for this window (starts cooldown)."""
    import datetime as _dt
    import pandas as _pd
    cfg = _COMBINED_CFG[month]
    try:
        fails = state.get(cfg["fail_key"])
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[cfg["fail_key"]] = fails
    except Exception:
        pass


def _render_combined_signals_table(st, state, month):
    """Combined signals table for September (9) or December (12).

    Best first: the BEST system's pick is shown whenever it has an
    entry at the latest check; the SECOND-BEST system's pick is
    shown ONLY when the best system has no entry at that check.
    Mirrors the incumbent panels' persistence: the most recent
    stored window stays visible until a newer window arrives.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    cfg = _COMBINED_CFG[month]
    try:
        hours = _combined_check_hours(month)
    except Exception:
        hours = {1: (11, 13, 17), 4: (16, 17, 18), 9: (1, 10, 11),
                 11: (9, 13, 15), 12: (10, 11, 13)}[month]
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(cfg["state_key"])
        if not isinstance(payload, dict):
            payload = None
        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None
        latest_win = _latest_entry_window_utc(now_utc, hours=hours)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win
                or _payload_data_failed(payload))
                and not _combined_recent_fail(latest_win, state, month)
                and _c22_data_loaded(state)):
            with st.spinner(f"Evaluating {cfg['month_name']} COMBINED signals..."):
                new_payload = _evaluate_combined_window(
                    state, month, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
                if _payload_data_failed(new_payload):
                    _combined_mark_fail(latest_win, state, month)
            else:
                _combined_mark_fail(latest_win, state, month)

        st.markdown(f"### \U0001F3AF {cfg['month_name']} COMBINED signals \u2014 "
                    f"Best first, Second-Best only when Best is silent")
        st.info(COMBINED_RULE_TEXT)
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info(f"Waiting for the first {cfg['month_name']} combined entry "
                    "window -- signals will appear here and stay visible until "
                    "a newer window arrives.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " \u00b7 <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            _window_header_html(payload, win_ts, age_min, mins_ago,
                                cfg["best_id"], live_tag),
            unsafe_allow_html=True,
        )
        disp = payload.get("signals")
        has_disp = isinstance(disp, _pd.DataFrame) and not disp.empty
        if has_disp:
            try:
                state[cfg["state_key"] + ":last_entry"] = {
                    "window_mmt": payload.get("window_mmt"),
                    "window_utc": payload.get("window_utc"),
                    "signals": disp,
                }
            except Exception:
                pass
            if payload.get("source") == "SECOND_BEST":
                st.warning(
                    f"\U0001F7E0 SECOND BEST pick -- the Best system "
                    f"({cfg['best_label']}) had NO entry at this check, so "
                    f"the Second-Best system ({cfg['second_label']}) pick "
                    "is shown.")
            else:
                st.success(
                    f"\U0001F7E2 BEST pick -- shown from the Best system "
                    f"({cfg['best_label']}). The Second-Best system was "
                    "not used because Best had an entry at this check.")
            st.table(_entry_row_colors(disp))
        else:
            n_eval = payload.get("n_evaluable", 20)
            if _payload_data_failed(payload):
                st.error(f"\u26a0\ufe0f Price data incomplete for this window -- only {n_eval}/20 symbols "
                         f"are ready. Check calculation is incomplete. "
                         f"Refreshing automatically; if it persists, check the data connection. {_diag_notes(payload)}")
            else:
                st.info(f"No entry at this check -- the Best system "
                        f"({cfg['best_label']}) had no entry, and the "
                        f"Second-Best system ({cfg['second_label']}) had "
                        "no entry either.")
        return payload
    except Exception:
        _p = state.get(_COMBINED_CFG[month]["state_key"])
        return _p if isinstance(_p, dict) else None


def _render_sep_combined_signals_table(st, state):
    return _render_combined_signals_table(st, state, 9)


def _render_dec_combined_signals_table(st, state):
    return _render_combined_signals_table(st, state, 12)


def _render_nov_combined_signals_table(st, state):
    return _render_combined_signals_table(st, state, 11)


def _render_jan_combined_signals_table(st, state):
    return _render_combined_signals_table(st, state, 1)


def _render_apr_combined_signals_table(st, state):
    return _render_combined_signals_table(st, state, 4)


def _render_combined_download_buttons(st, payload, month):
    """CSV + Excel downloads for the displayed combined signals."""
    cfg = _COMBINED_CFG[month]
    try:
        import pandas as _pd
        if not isinstance(payload, dict):
            return
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            return
        export = disp.copy()
        export["Window MMT"] = payload.get("window_mmt", "")
        export["Source"] = payload.get("source_label", "")
        export["Source system"] = payload.get("source_system", "")
        try:
            export["Evaluated (UTC)"] = _pd.Timestamp(
                payload.get("evaluated_at_utc")).strftime("%Y-%m-%d %H:%M")
        except Exception:
            export["Evaluated (UTC)"] = ""
        fname_base = f"{cfg['dl_base']}_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"{cfg['month_name']} combined CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label=f"\U0001F4E5 Download {cfg['month_name']} COMBINED signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key=f"dl_{cfg['sysid']}_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name=cfg["sheet"])
            st.download_button(
                label=f"\U0001F4E5 Download {cfg['month_name']} COMBINED signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_{cfg['sysid']}_xlsx_v1",
            )
        except Exception:
            pass
    except Exception:
        return


def render_sep_combined_download_buttons(st, payload):
    return _render_combined_download_buttons(st, payload, 9)


def render_dec_combined_download_buttons(st, payload):
    return _render_combined_download_buttons(st, payload, 12)


def render_nov_combined_download_buttons(st, payload):
    return _render_combined_download_buttons(st, payload, 11)


def render_jan_combined_download_buttons(st, payload):
    return _render_combined_download_buttons(st, payload, 1)


def render_apr_combined_download_buttons(st, payload):
    return _render_combined_download_buttons(st, payload, 4)


# ============================================================================
# The 12 standing monthly systems (2026-10-22 purge): panel wiring table.
# Month order Jan..Dec. The renderers/download buttons/state keys for every
# other cycle were deleted; only these 12 panels exist.
# ============================================================================

_MONTH_PANEL_ORDER = [
    # 12-system rebuild (2026-10-27): exactly ONE panel per month,
    # in month order -- the month's combined system where a second
    # best exists (Jan/Apr/Sep/Nov/Dec), else the best-only panel.
    # The third element names the BEST cycle module
    # (core.cycle<nn>_best / CYCLE<NN>_CHECK_HOURS) used by the
    # check-time reminders.
    ("January", "cycle60bcombined", "60b", "C60B+C60-03"),
    ("February", "cycle85", 85, "C85-23"),
    ("March", "cycle86", 86, "C86-24"),
    ("April", "cycle87bcombined", "87b", "C87B+C87-24"),
    ("May", "cycle88", 88, "C88-03"),
    ("June", "cycle89", 89, "C89-21"),
    ("July", "cycle78", 78, "C78-34"),
    ("August", "cycle67", 67, "C67-04"),
    ("September", "cycle91combined", 91, "C91-15+C287"),
    ("October", "cycle92", 92, "C92-24 + C155 dual-pick"),
    ("November", "cycle93bcombined", "93b", "C93B+C93-24"),
    ("December", "cycle94combined", "94b", "C94B+C274"),
]

_SIGNAL_PANELS = {
    "cycle85": {"render": _render_cycle85_signals_table,
                "download": render_cycle85_download_buttons,
                "state_key": _C85_SIG_STATE_KEY, "age_key": _C85_SIG_AGE_KEY,
                "diag_key": _C85_SIG_DIAG_KEY, "fail_key": _C85_SIG_FAIL_KEY,
                "label": "Cycle 85 (C85-23) \u2014 February system"},
    "cycle86": {"render": _render_cycle86_signals_table,
                "download": render_cycle86_download_buttons,
                "state_key": _C86_SIG_STATE_KEY, "age_key": _C86_SIG_AGE_KEY,
                "diag_key": _C86_SIG_DIAG_KEY, "fail_key": _C86_SIG_FAIL_KEY,
                "label": "Cycle 86 (C86-24) \u2014 March system"},
    "cycle88": {"render": _render_cycle88_signals_table,
                "download": render_cycle88_download_buttons,
                "state_key": _C88_SIG_STATE_KEY, "age_key": _C88_SIG_AGE_KEY,
                "diag_key": _C88_SIG_DIAG_KEY, "fail_key": _C88_SIG_FAIL_KEY,
                "label": "Cycle 88 (C88-03) \u2014 May system"},
    "cycle89": {"render": _render_cycle89_signals_table,
                "download": render_cycle89_download_buttons,
                "state_key": _C89_SIG_STATE_KEY, "age_key": _C89_SIG_AGE_KEY,
                "diag_key": _C89_SIG_DIAG_KEY, "fail_key": _C89_SIG_FAIL_KEY,
                "label": "Cycle 89 (C89-21) \u2014 June system"},
    "cycle78": {"render": _render_cycle78_signals_table,
                "download": render_cycle78_download_buttons,
                "state_key": _C78_SIG_STATE_KEY, "age_key": _C78_SIG_AGE_KEY,
                "diag_key": _C78_SIG_DIAG_KEY, "fail_key": _C78_SIG_FAIL_KEY,
                "label": "Cycle 78 (C78-34) \u2014 July system"},
    "cycle67": {"render": _render_cycle67_signals_table,
                "download": render_cycle67_download_buttons,
                "state_key": _C67_SIG_STATE_KEY, "age_key": _C67_SIG_AGE_KEY,
                "diag_key": _C67_SIG_DIAG_KEY, "fail_key": _C67_SIG_FAIL_KEY,
                "label": "Cycle 67 (C67-04) \u2014 August system"},
    "cycle92": {"render": _render_cycle92_signals_table,
                "download": render_cycle92_download_buttons,
                "state_key": _C92_SIG_STATE_KEY, "age_key": _C92_SIG_AGE_KEY,
                "diag_key": _C92_SIG_DIAG_KEY, "fail_key": _C92_SIG_FAIL_KEY,
                "label": "Cycle 155 dual-pick (on C92-24) \u2014 October BEST"},
    "cycle91combined": {"render": _render_sep_combined_signals_table,
                "download": render_sep_combined_download_buttons,
                "state_key": _COMBINED_CFG[9]["state_key"], "age_key": _COMBINED_CFG[9]["age_key"],
                "diag_key": _COMBINED_CFG[9]["diag_key"], "fail_key": _COMBINED_CFG[9]["fail_key"],
                "label": "September COMBINED (Best first, Second-Best only when Best is silent)"},
    "cycle94combined": {"render": _render_dec_combined_signals_table,
                "download": render_dec_combined_download_buttons,
                "state_key": _COMBINED_CFG[12]["state_key"], "age_key": _COMBINED_CFG[12]["age_key"],
                "diag_key": _COMBINED_CFG[12]["diag_key"], "fail_key": _COMBINED_CFG[12]["fail_key"],
                "label": "December COMBINED (Best first, Second-Best only when Best is silent)"},
    "cycle93bcombined": {"render": _render_nov_combined_signals_table,
                "download": render_nov_combined_download_buttons,
                "state_key": _COMBINED_CFG[11]["state_key"], "age_key": _COMBINED_CFG[11]["age_key"],
                "diag_key": _COMBINED_CFG[11]["diag_key"], "fail_key": _COMBINED_CFG[11]["fail_key"],
                "label": "November COMBINED (Best first, Second-Best only when Best is silent)"},
    "cycle60bcombined": {"render": _render_jan_combined_signals_table,
                "download": render_jan_combined_download_buttons,
                "state_key": _COMBINED_CFG[1]["state_key"], "age_key": _COMBINED_CFG[1]["age_key"],
                "diag_key": _COMBINED_CFG[1]["diag_key"], "fail_key": _COMBINED_CFG[1]["fail_key"],
                "label": "January COMBINED (Best first, Second-Best only when Best is silent)"},
    "cycle87bcombined": {"render": _render_apr_combined_signals_table,
                "download": render_apr_combined_download_buttons,
                "state_key": _COMBINED_CFG[4]["state_key"], "age_key": _COMBINED_CFG[4]["age_key"],
                "diag_key": _COMBINED_CFG[4]["diag_key"], "fail_key": _COMBINED_CFG[4]["fail_key"],
                "label": "April COMBINED (Best first, Second-Best only when Best is silent)"},
}

def render_multisymbol_regime_summary(
    st: Any,
    state: MutableMapping[str, Any],
) -> None:
    """Slim Field 3 page: banner + symbols box + signals table + reminders.

    Only the 12 standing monthly systems remain (2026-10-22 purge): the
    "Signal system" dropdown offers exactly Jan C60-03, Feb C85-23,
    Mar C86-24, Apr C87-24, May C88-03, Jun C89-21, Jul C78-34, Aug C67-04,
    Sep C91-15, Oct C92-24, Nov C93-24, Dec C94-23, and auto-defaults to the
    current month's system. Two recorded second-best systems
    (Sep cycle287, Dec cycle274; integrated 2026-10-25 under the
    user's chain+DSR waiver) are additionally selectable but are
    never the default. Two COMBINED panels (September, December;
    added 2026-10-26) apply the best-first rule: the month's BEST
    pick is shown, and the SECOND-BEST pick is shown only when Best
    has no entry at that check. Each system runs its winner equations at its
    own check hours with exactly 1 entry per check. Each entry window's
    signals are persisted in session state and stay visible until the next
    window arrives. The "Refresh the dashboard" button above the signals
    table forces a fresh H1 + M15 fetch and re-evaluation; the reminders
    section below the table lists the current month's check
    times with persistent checkbox toggles.
    """
    _auto_refresh_field3(st)
    from ui.monthly_equation_panel import render_monthly_panel
    # Shared data pipeline only (its expander UI is hidden); the signal
    # panels fetch their own H1/M15 frames via the provider chain.
    render_monthly_panel(st, state)
    _load_saved_if_needed(state)
    context = get_global_symbol_context(state)

    # Signal-system selector: the 12 standing monthly systems ONLY
    # (plus the appended second-best and COMBINED panels, which are
    # never the default).
    _combined_choice = None
    try:
        import datetime as _dtm
        from core.signal_mode import (MONTH_SYSTEMS as _MONTH_SYSTEMS,
                                      set_active_system as _set_active_system)
        if "signal_system" not in st.session_state:
            _mnow = _dtm.datetime.now(_dtm.timezone.utc).month
            # 12-system rebuild: default to the current month's ONE
            # panel (its combined system where one exists).
            st.session_state["signal_system"] = (
                _MONTH_PANEL_ORDER[_mnow - 1][1]
                if 1 <= _mnow <= 12 else "cycle92")
        _sys_choice = st.selectbox(
            "Signal system",
            options=[_sys for _m, _sys, _nn, _code in _MONTH_PANEL_ORDER],
            format_func=lambda v: _SIGNAL_PANELS[v]["label"],
            key="signal_system",
        )
        if _sys_choice in _COMBINED_CFG_SYSIDS:
            # Combined panel: keep the router's active system on the
            # month's BEST system (banner/hours stay the best's); the
            # panel itself applies the best-first combined rule.
            _combined_choice = _sys_choice
            _set_active_system(_COMBINED_CFG_BY_SYSID[_sys_choice]["best_id"])
        else:
            _set_active_system(_sys_choice)
    except Exception:
        pass

    if _combined_choice in _SIGNAL_PANELS:
        _active = _combined_choice
    else:
        try:
            from core.signal_mode import active_system as _active_system
            _active = _active_system()
        except Exception:
            _active = "cycle92"
    _panel = _SIGNAL_PANELS.get(_active) or _SIGNAL_PANELS["cycle92"]
    _render_cycle12_check_banner(st, state.get(_panel["age_key"]))
    # Combined Best + Second-Best rule (2026-10-26): shown at the top
    # of the signal panels area for every panel.
    try:
        st.info(COMBINED_RULE_TEXT)
    except Exception:
        pass
    _render_symbols_loaded_box(st, context)

    # Refresh button at the TOP of the ranking/signals table: forces a
    # fresh data fetch (H1 + M15) and a re-evaluation of the panel.
    try:
        if st.button("\U0001f504 Refresh the dashboard", key="refresh_dashboard_btn"):
            _force_dashboard_refresh(st, state)
    except Exception:
        pass

    payload = _panel["render"](st, state)

    # Downloads sit BELOW the signals table (full-width, mobile-friendly).
    if payload is not None:
        st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
        _panel["download"](st, payload)

    _render_eval_history(st, state, _active)

    _render_check_time_reminders(st, state)


# ============================================================================
# Public exports
# ============================================================================

__all__ = [
    "render_multisymbol_regime_summary",
    "render_middle_regime_download_button",


    "_age_only_ranking",
    "_middle_age_ranking",

    "get_ras_status",
    "get_strategy_decision",

    "_add_ras_decision_column",
    "_add_strategy_decision_column",
    "_add_weighted_risk_score",
    "_add_hourly_capped_risk_filter",

    "AGE_ONLY_RANK_COLUMN",
    "HIGHER_AGE_RANK_COLUMN",
    "HIGHER_AGE_DISPLAY_COLUMN",
    "FIELD3_CANONICAL_TABLES_KEY",
    "MIDDLE_AGE_RANK_COLUMN",
    "MIDDLE_AGE_DISPLAY_COLUMN",
    "MIDDLE_AVG_SOURCE_COLUMN",
    "AVG_REGIME_CANDLE_COLUMN",
    "MIDDLE_COMPLETED_SAMPLE_COLUMN",
    "COMPLETED_SAMPLE_DISPLAY_COLUMN",
    "CANDLE_STATISTICS_COLUMN",
    "RISK_SCORE_COLUMN",
    "IS_POTENTIAL_BLOCK_COLUMN",
    "HOURLY_BLOCK_COUNT_COLUMN",
    "FINAL_ACTION_COLUMN",
    "RISK_SCORE_THRESHOLD",
    "HOURLY_BLOCK_QUOTA",
    "WEIGHTED_RISK_SCORE_COLUMN",
    "WEIGHTED_RISK_DECISION_COLUMN",
    "WEIGHTED_RISK_THRESHOLD",
    "SL_DECISION_COLUMN",

    "RAS_DECISION_COLUMN",
    "STRATEGY_DECISION_COLUMN",
]

# Retained unrelated display/API constants from the original app.
S1_LABEL = "S1"
S2_LABEL = "S2"
S3_LABEL = "S3"
S4_LABEL = "S4"
NONE_LABEL = "None"
MIDDLE_HISTORY_STATE_KEY = (
    "field3_middle_regime_history_20260722"
)
FIELD_CLOSE_HIGHER_RANKING_KEY = (
    "field_close_higher_standard_regime_ranking"
)
FIELD_OPEN_HIGHER_RANKING_KEY = (
    "field_open_higher_standard_regime_ranking"
)
FIELD_CLOSE_HIGHER_MOBILE_KEY = (
    "field_close_higher_standard_regime_mobile"
)
FIELD_OPEN_HIGHER_MOBILE_KEY = (
    "field_open_higher_standard_regime_mobile"
)
FIELD_SECTION_ORDER_KEY = (
    "field3_field_section_order"
)
MIDDLE_NUMERIC_HIGHLIGHT_COLUMNS = [
    CANDLE_AGE_COLUMN,
    STARTING_PRICE_COLUMN,
    CANDLE_STATISTICS_COLUMN,
    RISK_SCORE_COLUMN,
    HOURLY_BLOCK_COUNT_COLUMN,
    WEIGHTED_RISK_SCORE_COLUMN,
    AVG_REGIME_CANDLE_COLUMN,
    COMPLETED_SAMPLE_DISPLAY_COLUMN,
]
