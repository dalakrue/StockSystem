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
    """Cached/provider H1 frame -> naive-UTC datetime-indexed OHLC (Open/High/Low/Close).

    Accepts the local candle-repository format (``open_time`` column) as
    well as provider-chain formats (``time``/``datetime``/``timestamp``).
    """
    try:
        import pandas as _pd
        if df is None or not isinstance(df, _pd.DataFrame) or df.empty:
            return None
        out = df.copy()
        tcol = next((c for c in ("time", "open_time", "Datetime", "datetime",
                                 "timestamp", "date")
                     if c in out.columns), None)
        if tcol is None:
            return None
        ts = _pd.to_datetime(out[tcol], errors="coerce")
        try:
            ts = ts.dt.tz_localize("UTC") if ts.dt.tz is None else ts.dt.tz_convert("UTC")
        except Exception:
            return None
        idx = _pd.DatetimeIndex(ts).tz_localize(None)
        out = out.drop(columns=[tcol])
        ren = {c: c.title() for c in ("open", "high", "low", "close") if c in out.columns}
        out = out.rename(columns=ren)
        if not all(c in out.columns for c in ("Open", "High", "Low", "Close")):
            return None
        out.index = idx
        out = out[~out.index.isna()].sort_index()
        out = out[~out.index.duplicated(keep="last")]
        return out if len(out) >= 50 else None
    except Exception:
        return None


def _render_symbols_loaded_box(st, context):
    """Small clean box: how many symbols were successfully loaded."""
    try:
        loaded = list(context.completed_symbols or context.loaded_symbols or [])
        configured = list(getattr(context, "configured_symbols", None) or [])
        failed = context.failed_symbols if isinstance(
            getattr(context, "failed_symbols", None), dict) else {}
        n_ok, n_cfg, n_fail = len(loaded), len(configured), len(failed)
        if n_cfg:
            txt = f"📊 <b>{n_ok}/{n_cfg}</b> symbols loaded"
        else:
            txt = f"📊 <b>{n_ok}</b> symbols loaded"
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


_C22_SIG_STATE_KEY = "cycle22_signals_latest_v2"
_C22_SIG_AGE_KEY = "cycle22_candle_age_txt"
_C22_SIG_DIAG_KEY = "cycle22_signals_diag_v2"
# Cycle 24 (R4A01) parallel state -- own keys so the Cycle 22 path is untouched.
_C24_SIG_STATE_KEY = "cycle24_signals_latest_v1"
_C24_SIG_AGE_KEY = "cycle24_candle_age_txt"
_C24_SIG_DIAG_KEY = "cycle24_signals_diag_v1"
_C24_SIG_FAIL_KEY = "cycle24_signals_fail_v1"
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
    """H1 frames for the 20 Cycle 22 symbols — LOCAL SQLITE CACHE FIRST.

    The app already loaded 20/20 symbols through the main pipeline; those
    candles sit in the local candle repository (same DB the provider chain
    itself uses). Reading them directly costs zero API calls, so it can
    never hit Twelve Data rate limits or burn the daily quota — the reason
    the old provider-chain loop silently produced zero frames in
    production. The provider chain remains a per-symbol fallback for the
    rare case the cache holds < 50 bars.

    need_candles: optional iterable of naive-UTC candle stamps that MUST be
    present (a check window's signal+entry stamps). The startup data load is
    one-time; without this, the cache goes stale ~1h later and every window
    evaluation silently returns empty ("no equations fired"). When needed
    candles are missing from most frames, fresh candles are fetched via the
    provider chain (only on window evaluations — never on plain rerenders —
    so API quota stays safe: ~20 credits/window, ~6 windows/day).

    Returns (frames dict, latest_candle_naive_utc or None, diag dict).
    """
    import pandas as _pd
    frames = {}
    latest_ts = None
    n_cache = 0
    n_live = 0
    live_errors = []
    repo = None
    try:
        from core.data.candle_repository import CandleRepository
        repo = CandleRepository()
    except Exception:
        repo = None
    for sym in _CYCLE22_PANEL_SYMBOLS:
        df = None
        if repo is not None:
            try:
                # completed_only=False: the engine needs the FORMING H:00 entry
                # candle (its open is fixed at candle start = backtest entry).
                # Signal features come from the earlier completed (H-1):00
                # candle, so the forming candle cannot contaminate them.
                # With completed_only=True the app could never evaluate a
                # window inside its 5-min entry (the H:00 candle completes at
                # H+1:00) and silently reported "no equations fired".
                cached = repo.load(sym, "H1", limit=400, completed_only=False)
                if cached is not None and len(cached) >= 50:
                    df = cached
                    n_cache += 1
            except Exception:
                df = None
        if df is None:
            try:
                from core.data.market_data_orchestrator import fetch_forex_candles_provider_chain
                live_df, _status, _trace = fetch_forex_candles_provider_chain(
                    sym, "H1", outputsize=300, state=state)
                if live_df is not None and not live_df.empty:
                    df = live_df
                    n_live += 1
                else:
                    live_errors.append(f"{sym}: {(_status or 'empty')}")
            except Exception as exc:
                live_errors.append(f"{sym}: {type(exc).__name__}")
        try:
            norm = _normalize_c22_frame(df)
        except Exception:
            norm = None
        if norm is not None:
            frames[sym] = norm
            try:
                ts = norm.index.max()
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
            except Exception:
                pass
    # Freshness-gated refresh: if the caller needs specific candles (a check
    # window's stamps) and they're missing from most frames, the one-time
    # startup cache has gone stale — fetch fresh via the provider chain.
    # This runs only on window evaluations (need_candles is None on plain
    # rerenders), so it cannot burn API quota in a refresh loop.
    if need_candles:
        try:
            need_set = set(_pd.Timestamp(c).tz_localize(None)
                           if _pd.Timestamp(c).tzinfo is None
                           else _pd.Timestamp(c).tz_convert("UTC").tz_localize(None)
                           for c in need_candles)
        except Exception:
            need_set = set()
        if need_set:
            missing_syms = []
            for sym in _CYCLE22_PANEL_SYMBOLS:
                norm = frames.get(sym)
                try:
                    if norm is None or not need_set.issubset(set(norm.index)):
                        missing_syms.append(sym)
                except Exception:
                    missing_syms.append(sym)
            if len(missing_syms) >= 4:
                try:
                    from core.data.market_data_orchestrator import fetch_forex_candles_provider_chain
                except Exception:
                    fetch_forex_candles_provider_chain = None
                if fetch_forex_candles_provider_chain is not None:
                    targets = (_CYCLE22_PANEL_SYMBOLS if len(missing_syms) > 10
                               else missing_syms)
                    for sym in targets:
                        try:
                            live_df, _st2, _tr2 = fetch_forex_candles_provider_chain(
                                sym, "H1", outputsize=300, state=state)
                            if live_df is not None and not live_df.empty:
                                norm2 = _normalize_c22_frame(live_df)
                                if norm2 is not None and len(norm2) >= 50:
                                    frames[sym] = norm2
                                    n_live += 1
                                    try:
                                        ts2 = norm2.index.max()
                                        if latest_ts is None or ts2 > latest_ts:
                                            latest_ts = ts2
                                    except Exception:
                                        pass
                                else:
                                    live_errors.append(f"{sym} refresh: normalized_empty")
                            else:
                                live_errors.append(f"{sym} refresh: {(_st2 or 'empty')}")
                        except Exception as exc:
                            live_errors.append(f"{sym} refresh: {type(exc).__name__}")
    diag = {"cache": n_cache, "live": n_live, "frames": len(frames),
            "live_errors": live_errors[:6]}
    return frames, latest_ts, diag


def _c22_signals_to_display(entries):
    """Add human TP/SL price columns to an evaluated signals frame."""
    import pandas as _pd
    from core.cycle12_best import pip_size as _pip_size
    if entries is None or not isinstance(entries, _pd.DataFrame) or entries.empty:
        return _pd.DataFrame(columns=["Symbol", "Direction", "Entry", "TP", "SL", "Score"])
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
            rows.append({
                "Symbol": sym,
                "Direction": d,
                "Entry": round(entry, dec),
                "TP": round(tp_x, dec),
                "SL": round(sl_x, dec),
                "Score": round(score, 1),
            })
        except Exception:
            continue
    return _pd.DataFrame(rows, columns=["Symbol", "Direction", "Entry", "TP", "SL", "Score"])


def _evaluate_c22_window(state, hour_utc, day=None):
    """Evaluate the 26 Cycle 22 equations for one entry window.

    Uses the exact backtest functions (evaluate_cycle22_signals +
    select_cycle22_entries with dynamic Rule A). Stores the result in
    session state keyed by window; returns the payload dict or None.

    ``day`` is the window's normalized UTC date (used when backfilling a
    past window, e.g. across a weekend); defaults to today.
    """
    import datetime as _dt
    import pandas as _pd
    from core.signal_mode import evaluate_signals, select_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        # The window needs its signal candle (H-1:00) and entry candle
        # (H:00, forming). Pass them so stale cache triggers a fresh fetch.
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C22_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            # Remember WHY so the UI can say it instead of a bare "waiting".
            try:
                state[_C22_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            sig = evaluate_signals(frames, check_label)
        except Exception:
            sig = _pd.DataFrame()
        try:
            entries = select_entries(sig, open_symbols=(), k=None)
        except Exception:
            entries = sig if isinstance(sig, _pd.DataFrame) else _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        # Data-health: how many symbols actually had BOTH needed candles.
        # A low count means empty results are broken data, not "no signal".
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            state[_C22_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


_C22_SIG_FAIL_KEY = "cycle22_signals_fail_v2"


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


def _c22_data_loaded(state):
    """True when the shared pipeline reports loaded symbols.

    Cheap gate for the (expensive) provider-chain fetch: with no data
    loaded there is nothing to evaluate.
    """
    try:
        ctx = get_global_symbol_context(state)
        return len(list(ctx.completed_symbols or ctx.loaded_symbols or [])) > 0
    except Exception:
        return False


def _c22_recent_fail(window_utc, state, cool_minutes=10):
    """True if this window's evaluation failed within the cooldown.

    Prevents 20 wasted API calls on every 30s rerun when evaluation
    keeps failing (e.g. provider outage).
    """
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C22_SIG_FAIL_KEY)
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


def _c22_mark_fail(window_utc, state):
    """Record a failed evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C22_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C22_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle22_signals_table(st, state):
    """THE signals table: Cycle 22 only, backfilled + persisted.

    - On EVERY render, computes the latest entry window <= now. If no
      signals are stored for it and H1 data is loaded, the window is
      evaluated IMMEDIATELY (backtest-identical: features from the
      completed (H-1):00 candle, entry = H:00 open), stored, displayed.
    - Displays the most recent stored window for UP TO 2 HOURS after the
      window time, or until a newer window arrives (whichever is first).
      After 2 h with no newer window, the table shows a waiting notice.
    - Never renders the old monthly S1-S240 table.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C22_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        # Backfill: the latest window at/before now, even if its 5-minute
        # live window already passed (e.g. user opens the app 51 min late).
        latest_win = _latest_entry_window_utc(now_utc)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win)
                and not _c22_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 22 signals…"):
                new_payload = _evaluate_c22_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
            else:
                _c22_mark_fail(latest_win, state)

        st.markdown("### 🎯 Cycle 22 signals")
        # 2-HOUR DISPLAY RULE: a window's signals stay visible for up to
        # 2 hours after the WINDOW time (not the evaluation time, so a
        # late backfill still expires on schedule), or until a newer
        # window arrives and replaces them — whichever comes first.
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first entry window — signals will appear here "
                    "and stay visible for up to 2 hours.")
            # If an evaluation was attempted and failed, say WHY instead of
            # leaving the user guessing (e.g. 0/20 frames from cache+live).
            try:
                diag = state.get(_C22_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"⚠️ Last Cycle 22 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        if age_min > 120:
            st.info("The last window's signals have expired after 2 hours — "
                    "waiting for the next entry window.")
            return None
        expires_in = max(0, 120 - age_min)
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " · <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            f"<div style='font-size:13px;color:#334155;margin:-6px 0 8px 0;'>"
            f"Window <b>{payload.get('window_mmt', '—')} MMT</b> · "
            f"evaluated {mins_ago} min ago · {payload.get('n_symbols', '—')} symbols · "
            f"visible {expires_in} more min{live_tag}</div>",
            unsafe_allow_html=True,
        )
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if n_eval < 10:
                st.error(f"⚠️ Price data incomplete for this window — only {n_eval}/20 symbols "
                         f"had the needed candles. This is a data problem, not a signal. "
                         f"Refreshing automatically; if it persists, check the data connection.")
            else:
                st.info("No Cycle 22 equations fired in this window.")
        else:
            st.dataframe(disp, use_container_width=True, hide_index=True)
        return payload
    except Exception:
        return state.get(_C22_SIG_STATE_KEY) if isinstance(state.get(_C22_SIG_STATE_KEY), dict) else None


def render_cycle22_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 22 signals."""
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
        fname_base = f"cycle22_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 22 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="📥 Download Cycle 22 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle22_csv_v2",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle22")
            st.download_button(
                label="📥 Download Cycle 22 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle22_xlsx_v2",
            )
        except Exception:
            pass
    except Exception:
        return




# ============================================================================
# Cycle 24 (R4A01) signals table -- parallel to the Cycle 22 path above.
# Own session-state keys; the working Cycle 22 code is NOT refactored.
# ============================================================================

def _evaluate_c24_window(state, hour_utc, day=None):
    """Evaluate the 24 Cycle 24 (R4A01) equations for one entry window.

    Calls core.cycle24_best directly (not the signal router) so the result
    is always the C24 system regardless of the active mode. Exactly 1
    entry per check (top-1 by score). Stores the result in session state
    keyed by window; returns the payload dict or None.
    """
    import datetime as _dt
    import pandas as _pd
    from core.cycle24_best import evaluate_cycle24_signals, select_cycle24_entries
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        day = (_pd.Timestamp(day).normalize() if day is not None
               else _pd.Timestamp(now_utc).normalize())
        check_label = day + _pd.Timedelta(hours=int(hour_utc), minutes=30)
        # The window needs its signal candle (H-1:00) and entry candle
        # (H:00, forming). Pass them so stale cache triggers a fresh fetch.
        need = [check_label - _pd.Timedelta(hours=1, minutes=30),
                check_label - _pd.Timedelta(minutes=30)]
        frames, latest_ts, diag = _fetch_c22_frames(state, need_candles=need)
        if latest_ts is not None:
            try:
                age_min = (now_utc - latest_ts.to_pydatetime()
                           if hasattr(latest_ts, "to_pydatetime") else now_utc - latest_ts
                           ).total_seconds() / 60.0
                if age_min >= 0:
                    state[_C24_SIG_AGE_KEY] = f"{age_min:.0f}m old"
            except Exception:
                pass
        if not frames:
            try:
                state[_C24_SIG_DIAG_KEY] = dict(diag or {})
            except Exception:
                pass
            return None
        try:
            sig = evaluate_cycle24_signals(frames, check_label)
        except Exception:
            sig = _pd.DataFrame()
        try:
            entries = select_cycle24_entries(sig, open_symbols=())
        except Exception:
            entries = sig if isinstance(sig, _pd.DataFrame) else _pd.DataFrame()
        if not isinstance(entries, _pd.DataFrame):
            entries = _pd.DataFrame()
        # Data-health: how many symbols actually had BOTH needed candles.
        # A low count means empty results are broken data, not "no signal".
        try:
            _need_set = set(_pd.Timestamp(c).tz_localize(None) for c in need)
            n_evaluable = sum(1 for f in frames.values()
                              if f is not None and _need_set.issubset(set(f.index)))
        except Exception:
            n_evaluable = 0
        payload = {
            "window_utc": day + _pd.Timedelta(hours=int(hour_utc)),
            "window_mmt": _c22_window_mmt_label(hour_utc),
            "evaluated_at_utc": now_utc,
            "n_symbols": len(frames),
            "n_evaluable": n_evaluable,
            "signals": _c22_signals_to_display(entries),
        }
        try:
            state[_C24_SIG_STATE_KEY] = payload
        except Exception:
            pass
        return payload
    except Exception:
        return None


def _c24_recent_fail(window_utc, state, cool_minutes=10):
    """True if this C24 window's evaluation failed within the cooldown."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C24_SIG_FAIL_KEY)
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


def _c24_mark_fail(window_utc, state):
    """Record a failed C24 evaluation for this window (starts the cooldown)."""
    import datetime as _dt
    import pandas as _pd
    try:
        fails = state.get(_C24_SIG_FAIL_KEY)
        if not isinstance(fails, dict):
            fails = {}
        key = _pd.Timestamp(window_utc).strftime("%Y-%m-%dT%H:%M")
        fails[key] = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat()
        state[_C24_SIG_FAIL_KEY] = fails
    except Exception:
        pass


def _render_cycle24_signals_table(st, state):
    """Cycle 24 signals table: backfilled + persisted, exactly 1 entry/check.

    Mirrors _render_cycle22_signals_table: on EVERY render, computes the
    latest C24 entry window <= now (hours 15/17/18 UTC); if no signals
    are stored for it and H1 data is loaded, the window is evaluated
    IMMEDIATELY (backtest-identical), stored, displayed. The most recent
    stored window stays visible for UP TO 2 HOURS after the window time,
    or until a newer window arrives -- whichever is first.
    Returns the payload dict (or None) for the download buttons.
    """
    import datetime as _dt
    import pandas as _pd
    try:
        now_utc = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
        payload = state.get(_C24_SIG_STATE_KEY)
        if not isinstance(payload, dict):
            payload = None

        stored_win = None
        if payload is not None:
            try:
                stored_win = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                stored_win = None

        # Backfill: the latest C24 window at/before now, even if its
        # 5-minute live window already passed.
        latest_win = _latest_entry_window_utc(now_utc, hours=_C24_CHECK_HOURS)
        fresh_this_window = False
        if (latest_win is not None
                and (stored_win is None or stored_win != latest_win)
                and not _c24_recent_fail(latest_win, state)
                and _c22_data_loaded(state)):
            with st.spinner("Evaluating Cycle 24 signals…"):
                new_payload = _evaluate_c24_window(
                    state, int(latest_win.hour), day=latest_win.normalize())
            if new_payload is not None:
                payload = new_payload
                fresh_this_window = True
            else:
                _c24_mark_fail(latest_win, state)

        st.markdown("### 🎯 Cycle 24 signals")
        # 2-HOUR DISPLAY RULE (same as Cycle 22): a window's signals stay
        # visible for up to 2 hours after the WINDOW time, or until a
        # newer window arrives -- whichever comes first.
        win_ts = None
        if payload is not None:
            try:
                win_ts = _pd.Timestamp(payload.get("window_utc")).tz_localize(None)
            except Exception:
                win_ts = None
        if payload is None or win_ts is None:
            st.info("Waiting for the first Cycle 24 entry window — signals will "
                    "appear here and stay visible for up to 2 hours.")
            try:
                diag = state.get(_C24_SIG_DIAG_KEY)
            except Exception:
                diag = None
            if isinstance(diag, dict) and diag.get("frames", 0) == 0 and \
                    (diag.get("cache", 0) or diag.get("live", 0) or diag.get("live_errors")):
                errs = diag.get("live_errors") or []
                detail = (f" Provider notes: {'; '.join(errs)}" if errs else "")
                st.warning(
                    f"⚠️ Last Cycle 24 evaluation built 0 price frames "
                    f"(local cache {diag.get('cache', 0)}/20, live {diag.get('live', 0)}/20)."
                    f"{detail} Retrying automatically.")
            return None
        age_min = int((now_utc - win_ts).total_seconds() // 60)
        if age_min > 120:
            st.info("The last Cycle 24 window's signals have expired after 2 hours — "
                    "waiting for the next entry window.")
            return None
        expires_in = max(0, 120 - age_min)
        try:
            mins_ago = max(0, int((now_utc - payload["evaluated_at_utc"]).total_seconds() // 60))
        except Exception:
            mins_ago = 0
        live_tag = " · <b style='color:#16a34a;'>LIVE</b>" if fresh_this_window else ""
        st.markdown(
            f"<div style='font-size:13px;color:#334155;margin:-6px 0 8px 0;'>"
            f"Window <b>{payload.get('window_mmt', '—')} MMT</b> · "
            f"evaluated {mins_ago} min ago · {payload.get('n_symbols', '—')} symbols · "
            f"visible {expires_in} more min{live_tag}</div>",
            unsafe_allow_html=True,
        )
        disp = payload.get("signals")
        if disp is None or not isinstance(disp, _pd.DataFrame) or disp.empty:
            n_eval = payload.get("n_evaluable", 20)
            if n_eval < 10:
                st.error(f"⚠️ Price data incomplete for this window — only {n_eval}/20 symbols "
                         f"had the needed candles. This is a data problem, not a signal. "
                         f"Refreshing automatically; if it persists, check the data connection.")
            else:
                st.info("No Cycle 24 equations fired in this window.")
        else:
            st.dataframe(disp, use_container_width=True, hide_index=True)
        return payload
    except Exception:
        return state.get(_C24_SIG_STATE_KEY) if isinstance(state.get(_C24_SIG_STATE_KEY), dict) else None


def render_cycle24_download_buttons(st, payload):
    """CSV + Excel downloads for the displayed Cycle 24 signals."""
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
        fname_base = f"cycle24_signals_{payload.get('window_mmt', 'na').replace(':', '')}MMT"
        try:
            csv = export.to_csv(index=False, encoding="utf-8")
        except Exception as exc:
            st.error(f"Cycle 24 CSV could not be prepared: {type(exc).__name__}: {exc}")
            csv = None
        if csv is not None:
            st.download_button(
                label="📥 Download Cycle 24 signals CSV",
                data=csv,
                file_name=f"{fname_base}.csv",
                mime="text/csv",
                key="dl_cycle24_csv_v1",
            )
        try:
            from io import BytesIO as _Bio
            bio = _Bio()
            with _pd.ExcelWriter(bio, engine="openpyxl") as _xw:
                export.to_excel(_xw, index=False, sheet_name="Cycle24")
            st.download_button(
                label="📥 Download Cycle 24 signals Excel",
                data=bio.getvalue(),
                file_name=f"{fname_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_cycle24_xlsx_v1",
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
        from streamlit_autorefresh import st_autorefresh

        st_autorefresh(interval=interval_ms, limit=None, key="field3_c22_refresh")
    except Exception:
        st.markdown(
            '<meta http-equiv="refresh" content="30">',
            unsafe_allow_html=True,
        )


def render_multisymbol_regime_summary(
    st: Any,
    state: MutableMapping[str, Any],
) -> None:
    """Slim Field 3 page: banner + symbols box + signals table.

    The old monthly S1-S240 regime ranking table has been removed from the
    UI entirely. Default mode shows the Cycle 24 (R4A01) table -- 24
    equations, 3 check hours (15/17/18 UTC = 21:30/23:30/00:30 MMT),
    exactly 1 entry per check; the "Signal system" dropdown above the
    banner switches back to the Cycle 22 table (26 equations, ATR-based
    TP/SL, backtest-matched). Each entry window's signals
    are persisted in session state and stay visible for up to 2 hours
    (or until the next window arrives).
    """
    _auto_refresh_field3(st)
    from ui.monthly_equation_panel import render_monthly_panel
    # Shared data pipeline only (its expander UI is hidden); Cycle 22
    # fetches its own H1 frames via the provider chain below.
    render_monthly_panel(st, state)
    _load_saved_if_needed(
        state
    )

    context = (
        get_global_symbol_context(
            state
        )
    )

    # Signal-system selector. The router default is Cycle 24 (R4A01), but
    # the user can switch back to Cycle 22 (F1-P4). Only the two systems
    # with dedicated, verified table renderers are offered here (cycle18 /
    # ft-c01 have no table renderer, so offering them would show the wrong
    # table). The choice is applied to the router on EVERY render, BEFORE
    # the banner and the signals table read active_system().
    try:
        from core.signal_mode import set_active_system as _set_active_system
        if "signal_system" not in st.session_state:
            st.session_state["signal_system"] = "cycle24"
        _sys_choice = st.selectbox(
            "Signal system",
            options=["cycle24", "cycle22"],
            format_func=lambda v: (
                "Cycle 24 (R4A01) — October system" if v == "cycle24"
                else "Cycle 22 (F1-P4) — broad system"),
            key="signal_system",
        )
        _set_active_system(_sys_choice)
    except Exception:
        pass

    try:
        from core.signal_mode import active_system as _active_system
        _mode_is_c24 = (_active_system() == "cycle24")
    except Exception:
        _mode_is_c24 = False
    _render_cycle12_check_banner(
        st, state.get(_C24_SIG_AGE_KEY if _mode_is_c24 else _C22_SIG_AGE_KEY))
    _render_symbols_loaded_box(st, context)
    # Signals table follows the active system: Cycle 24 renders its own
    # table (own state keys, 3 check hours, exactly 1 entry/check);
    # every other mode keeps the proven Cycle 22 table untouched.
    if _mode_is_c24:
        payload = _render_cycle24_signals_table(st, state)
    else:
        payload = _render_cycle22_signals_table(st, state)

    # Downloads sit BELOW the signals table (full-width, mobile-friendly).
    if payload is not None:
        st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
        if _mode_is_c24:
            render_cycle24_download_buttons(st, payload)
        else:
            render_cycle22_download_buttons(st, payload)


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
