"""Unified Lunch trust history (additive research/display layer).

The builder consumes already-published Lunch/canonical frames and completed OHLC
only.  It never mutates production calculations or Table 3.  Where a published
value is unavailable, an explicitly labelled local research fallback may be
computed from completed candles; unavailable inputs stay missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import re
from typing import Any, Mapping, MutableMapping

import numpy as np
import pandas as pd

VERSION = "LUNCH-TRUST-HISTORY-0.3.0-TIME-SYNC-20260630"
CACHE_KEY = "lunch_unified_trust_history_cache_20260628"
FRAME_KEY = "lunch_unified_trust_history_20260628"
ALLOWED_PROTECTIVE_ACTIONS = {
    "ALLOWED", "WAIT FOR PULLBACK", "HOLD AND PROTECT", "NO TRADE"
}

IDENTITY_COLUMNS = [
    "Completed Broker Candle", "Broker Day", "Broker Hour", "Symbol", "Timeframe",
    "Session", "Source", "Run ID", "Generation ID", "Source Version",
    "Data Coverage %", "Data-Quality Status", "Missingness Reason", "Validation Status",
]
PREDICTION_COLUMNS = [
    "Blue Path Direction", "Blue Path Value", "Blue Path Trust /10", "Blue Path Rank",
    "Red Path Direction", "Red Path Value", "Red Path Trust /10", "Red Path Rank",
    *[item for h in (1, 2, 3, 6) for item in (
        f"H+{h} Predicted Price", f"H+{h} Actual Matured Price", f"H+{h} Error",
        f"H+{h} Trust /10", f"H+{h} Rank",
    )],
    "Next-H1 Lower Bound", "Next-H1 Upper Bound", "Interval Coverage", "Interval Width",
    "Interval Trust /10", "Path Stability /10", "Direction Agreement /10",
    "Uncertainty %", "Changepoint Warning",
]
REGIME_COLUMNS: list[str] = []
for _label in ("Lower", "Middle", "Higher"):
    REGIME_COLUMNS.extend([
        f"{_label} Regime", f"{_label} Alpha", f"{_label} Beta", f"{_label} Delta",
        f"{_label} Regime Age", f"{_label} Expected Duration",
        f"{_label} Expected Remaining Duration", f"{_label} Transition Probability",
        f"{_label} Hierarchy Agreement", f"{_label} Uncertainty",
        f"{_label} Reliability", f"{_label} Trust /10", f"{_label} Rank",
        f"{_label} Data-Quality Status",
    ])
DECISION_COLUMNS = [
    *[item for label in (
        "Entry", "Buy Pressure", "Sell Pressure", "Net Pressure", "Pullback",
        "M1", "Master Decision", "Hold Safety", "TP Quality", "Direction Confirmation",
    ) for item in (label if label.endswith("Decision") else f"{label} Decision", f"{label} Trust /10", f"{label} Rank")],
    "Original Production Direction", "Protective Action", "Protective Reason",
]
# User-facing aliases expected by the specification.
DECISION_RENAMES = {
    "Entry Decision": "Entry Decision",
    "Buy Pressure Decision": "Buy Pressure",
    "Sell Pressure Decision": "Sell Pressure",
    "Net Pressure Decision": "Net Pressure",
    "Pullback Decision": "Pullback Readiness",
    "M1 Decision": "M1 Confirmation",
    "Master Decision": "Master Decision",
    "Hold Safety Decision": "Hold Safety",
    "TP Quality Decision": "TP Quality",
    "Direction Confirmation Decision": "Direction Confirmation",
}

COLUMN_GROUPS = {
    "Identity": IDENTITY_COLUMNS,
    "Predictions": ["Completed Broker Candle", *PREDICTION_COLUMNS],
    "Regimes": ["Completed Broker Candle", *REGIME_COLUMNS],
    "Decisions": ["Completed Broker Candle", *[DECISION_RENAMES.get(c, c) for c in DECISION_COLUMNS]],
    "Protection": [
        "Completed Broker Candle", "Original Production Direction", "Master Decision",
        "Master Decision Trust /10", "Hold Safety", "TP Quality", "Direction Confirmation",
        "Protective Action", "Protective Reason", "Data Coverage %", "Data-Quality Status",
    ],
}


def _norm(value: Any) -> str:
    if _missing(value):
        value = ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "N/A", "NA", "NONE", "NAN", "UNAVAILABLE", "—", "-"}
    try:
        flag = pd.isna(value)
        return bool(flag) if isinstance(flag, (bool, np.bool_)) else False
    except Exception:
        return False


def _first(*values: Any, default: Any = None) -> Any:
    for value in values:
        if not _missing(value):
            return value
    return default


def _find_col(frame: pd.DataFrame, aliases: tuple[str, ...] | list[str]) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {_norm(column): str(column) for column in frame.columns}
    for alias in aliases:
        key = _norm(alias)
        if key in normalized:
            return normalized[key]
    for alias in aliases:
        key = _norm(alias)
        for normalized_name, original in normalized.items():
            if key and (key in normalized_name or normalized_name in key):
                return original
    return None


def _time_col(frame: pd.DataFrame) -> str | None:
    return _find_col(frame, [
        "Completed Broker Candle", "Broker Candle Time", "Broker Candle", "Time",
        "Datetime", "Timestamp", "event_time_utc", "Date Time", "Date",
    ])


def _series(frame: pd.DataFrame, aliases: tuple[str, ...] | list[str], *, numeric: bool = False) -> pd.Series:
    column = _find_col(frame, aliases)
    if column is None:
        return pd.Series(pd.NA, index=frame.index, dtype="Float64" if numeric else "object")
    output = frame[column]
    if numeric:
        return pd.to_numeric(output, errors="coerce")
    return output.astype("object")


def _utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", utc=True, format="mixed")


def _broker_offset_minutes(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> int:
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        clock = shared_broker_time_provider(state, canonical=canonical)
        value = clock.get("broker_offset_minutes")
        if value is not None:
            return int(round(float(value)))
    except Exception:
        pass
    for key in ("broker_offset_minutes", "broker_offset_minutes_20260622"):
        value = canonical.get(key)
        if not _missing(value):
            try:
                return int(round(float(value)))
            except Exception:
                pass
    for key in ("manual_broker_utc_offset_hours_20260622", "mt5_broker_utc_offset_hours_20260622", "broker_utc_offset_hours", "mt5_server_utc_offset_hours"):
        value = state.get(key)
        if not _missing(value):
            try:
                return int(round(float(value) * 60.0))
            except Exception:
                pass
    return 0


def _direction(value: Any) -> float:
    text = _norm(value).upper()
    has_buy = bool(re.search(r"\b(BUY|BULL|UP|LONG)\b", text))
    has_sell = bool(re.search(r"\b(SELL|BEAR|DOWN|SHORT)\b", text))
    if has_buy and not has_sell:
        return 1.0
    if has_sell and not has_buy:
        return -1.0
    return 0.0


def _direction_text(values: pd.Series, reference: pd.Series) -> pd.Series:
    delta = pd.to_numeric(values, errors="coerce") - pd.to_numeric(reference, errors="coerce")
    return pd.Series(np.select([delta > 0, delta < 0], ["BUY", "SELL"], default="WAIT"), index=values.index, dtype="object")


def _grade(value: Any) -> str:
    try:
        score = float(value)
    except Exception:
        return "N/A"
    if not math.isfinite(score):
        return "N/A"
    if score >= 9:
        return "A+"
    if score >= 8:
        return "A"
    if score >= 7:
        return "B"
    if score >= 6:
        return "C"
    if score >= 5:
        return "D"
    return "E"


def _expanding_percentile(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    out: list[Any] = []
    history: list[float] = []
    for value in values:
        if not math.isfinite(value):
            out.append(pd.NA)
            continue
        history.append(value)
        arr = np.asarray(history, dtype=float)
        out.append(float(np.mean(arr <= value) * 100.0))
    return pd.Series(out, index=series.index, dtype="Float64")


def _rank_labels(series: pd.Series) -> pd.Series:
    percentiles = _expanding_percentile(series)
    labels = []
    for value, percentile in zip(series, percentiles):
        if _missing(value) or _missing(percentile):
            labels.append("N/A")
        else:
            labels.append(f"{_grade(value)} · P{int(round(float(percentile))):02d}")
    return pd.Series(labels, index=series.index, dtype="object")


def _rolling_trust(
    quality: pd.Series,
    *,
    maturity_horizon: int,
    direction_hit: pd.Series | None = None,
    coverage: pd.Series | None = None,
    minimum: int = 12,
    window: int = 120,
) -> tuple[pd.Series, pd.Series]:
    """Create time-safe trust using outcomes only after their maturity candle."""
    q = pd.to_numeric(quality, errors="coerce").clip(0.0, 1.0)
    matured_q = q.shift(int(max(0, maturity_horizon)))
    q_mean = matured_q.rolling(window, min_periods=minimum).mean()
    count = matured_q.rolling(window, min_periods=1).count()
    terms = [(0.55, q_mean)]
    if direction_hit is not None:
        d = pd.to_numeric(direction_hit, errors="coerce").clip(0.0, 1.0).shift(int(max(0, maturity_horizon)))
        terms.append((0.25, d.rolling(window, min_periods=minimum).mean()))
    if coverage is not None:
        c = pd.to_numeric(coverage, errors="coerce").clip(0.0, 1.0).shift(int(max(0, maturity_horizon)))
        terms.append((0.10, c.rolling(window, min_periods=minimum).mean()))
    sample_score = (count / float(max(minimum, 1) * 2)).clip(0.0, 1.0)
    terms.append((0.10, sample_score))
    total_weight = sum(weight for weight, _ in terms)
    trust = sum(weight * value for weight, value in terms) / total_weight * 10.0
    trust = trust.where(count >= minimum).round(3)
    return trust.astype("Float64"), count.astype("Int64")


def _session_from_hour(hour: pd.Series) -> pd.Series:
    # Broad broker-hour labels; no direction is inferred from the session.
    conditions = [hour.between(0, 5), hour.between(6, 11), hour.between(12, 15), hour.between(16, 20)]
    values = ["TOKYO_SYDNEY", "LONDON", "LONDON_NEW_YORK_OVERLAP", "NEW_YORK"]
    return pd.Series(np.select(conditions, values, default="ROLLOVER"), index=hour.index, dtype="object")


def _market_candidates(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> list[pd.DataFrame]:
    candidates: list[pd.DataFrame] = []
    keys = (
        "canonical_completed_ohlc_df_20260617", "ohlc_df", "market_frame", "last_df",
        "shared_market_df", "df", "eurusd_h1_df", "normalized_market_data", "dv_pp_df",
    )
    for root in (canonical, canonical.get("market") if isinstance(canonical.get("market"), Mapping) else {}, state):
        if not isinstance(root, Mapping):
            continue
        for key in keys:
            value = root.get(key)
            if isinstance(value, pd.DataFrame) and not value.empty:
                candidates.append(value)
    return sorted(candidates, key=len, reverse=True)


def _prepare_ohlc(state: Mapping[str, Any], canonical: Mapping[str, Any], overall: pd.DataFrame) -> pd.DataFrame:
    candidates = [overall] if isinstance(overall, pd.DataFrame) and not overall.empty else []
    candidates.extend(_market_candidates(state, canonical))
    for source in candidates:
        time_column = _time_col(source)
        close_column = _find_col(source, ["Close", "close", "Last", "Price"])
        if time_column is None or close_column is None:
            continue
        out = pd.DataFrame({"time": _utc_series(source[time_column]), "close": pd.to_numeric(source[close_column], errors="coerce")})
        for target, aliases in {
            "open": ["Open", "open"], "high": ["High", "high"], "low": ["Low", "low"],
            "volume": ["Volume", "Tick Volume", "volume"],
        }.items():
            column = _find_col(source, aliases)
            out[target] = pd.to_numeric(source[column], errors="coerce") if column else np.nan
        out = out.dropna(subset=["time", "close"]).sort_values("time", kind="mergesort")
        out["time"] = out["time"].dt.floor("h")
        out = out.drop_duplicates("time", keep="last")
        if out.empty:
            continue
        out["open"] = out["open"].fillna(out["close"].shift(1)).fillna(out["close"])
        out["high"] = out[["open", "close", "high"]].max(axis=1, skipna=True)
        out["low"] = out[["open", "close", "low"]].min(axis=1, skipna=True)
        return out.reset_index(drop=True)
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])


def _last_25_broker_days(frame: pd.DataFrame, state: Mapping[str, Any], canonical: Mapping[str, Any], max_rows: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    offset = _broker_offset_minutes(state, canonical)
    broker_time = (frame["time"] + pd.to_timedelta(offset, unit="m")).dt.tz_localize(None)
    days = broker_time.dt.strftime("%Y-%m-%d")
    unique = list(dict.fromkeys(days.iloc[::-1].tolist()))[:25]
    result = frame.loc[days.isin(unique)].tail(max_rows).copy()
    result["broker_time"] = (result["time"] + pd.to_timedelta(offset, unit="m")).dt.tz_localize(None)
    return result.reset_index(drop=True)


def _merge_overall(base: pd.DataFrame, overall: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(overall, pd.DataFrame) or overall.empty:
        return base
    time_column = _time_col(overall)
    if time_column is None:
        return base
    source = overall.copy(deep=False)
    source["__time"] = _utc_series(source[time_column]).dt.floor("h")
    source = source.dropna(subset=["__time"]).drop_duplicates("__time", keep="first")
    source = source.drop(columns=[time_column], errors="ignore")
    # Keep the canonical OHLC calculation columns authoritative.  Published
    # columns with identical names remain available under an audit prefix.
    collisions = {column: f"Published {column}" for column in source.columns if column in base.columns and column != "__time"}
    if collisions:
        source = source.rename(columns=collisions)
    return base.merge(source, left_on="time", right_on="__time", how="left").drop(columns=["__time"], errors="ignore")


def _merge_factor_histories(base: pd.DataFrame, histories: Mapping[str, pd.DataFrame] | None) -> pd.DataFrame:
    output = base
    mapping = {
        "Entry Strength": "Entry", "BUY Pressure": "Buy Pressure", "SELL Pressure": "Sell Pressure",
        "Net Pressure": "Net Pressure", "Pullback Readiness": "Pullback", "M1 Confirmation": "M1",
        "Master Decision": "Master Decision", "Hold Safety": "Hold Safety", "TP Quality": "TP Quality",
        "Direction Confirmation": "Direction Confirmation",
    }
    histories = histories or {}
    for published_name, prefix in mapping.items():
        frame = histories.get(published_name)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        time_column = _time_col(frame)
        if time_column is None:
            continue
        source = frame.copy(deep=False)
        source["__time"] = _utc_series(source[time_column]).dt.floor("h")
        decision_column = _find_col(source, ["Decision", published_name, "Direction", "Label", "Action"])
        score_column = _find_col(source, ["Score /10", "Score", f"{published_name}/10", published_name])
        keep = ["__time"]
        rename: dict[str, str] = {}
        if decision_column:
            keep.append(decision_column)
            rename[decision_column] = f"__{prefix}_decision"
        if score_column and score_column != decision_column:
            keep.append(score_column)
            rename[score_column] = f"__{prefix}_score"
        source = source[keep].dropna(subset=["__time"]).drop_duplicates("__time", keep="first").rename(columns=rename)
        output = output.merge(source, left_on="time", right_on="__time", how="left").drop(columns=["__time"], errors="ignore")
    return output


def _regime_run_age(labels: pd.Series) -> pd.Series:
    change = labels.ne(labels.shift(1)).cumsum()
    return labels.groupby(change).cumcount().add(1).astype("Int64")


def _regime_features(close: pd.Series, returns: pd.Series, window: int, name: str) -> pd.DataFrame:
    minimum = max(8, min(window // 4, 40))
    mean = returns.rolling(window, min_periods=minimum).mean()
    volatility = returns.rolling(window, min_periods=minimum).std()
    signal = (mean / volatility.replace(0, np.nan)).clip(-3, 3)
    regime = pd.Series(np.select([signal > 0.12, signal < -0.12], ["BULL", "BEAR"], default="RANGE"), index=close.index, dtype="object")
    regime = regime.where(signal.notna(), pd.NA)
    age = _regime_run_age(regime.fillna("UNAVAILABLE"))
    # Time-safe expected duration: median of previously completed runs only.
    run_id = regime.fillna("UNAVAILABLE").ne(regime.fillna("UNAVAILABLE").shift()).cumsum()
    completed_durations = run_id.groupby(run_id).transform("size")
    duration_observed = completed_durations.where(run_id.ne(run_id.iloc[-1] if len(run_id) else -1))
    expected = duration_observed.expanding(min_periods=3).median().shift(1).fillna(window / 4.0)
    remaining = (expected - age.astype(float)).clip(lower=0)
    transition = (1.0 - np.exp(-age.astype(float) / expected.replace(0, np.nan))).clip(0, 1) * 100.0
    persistence = regime.fillna("UNAVAILABLE").eq(regime.shift(1).fillna("UNAVAILABLE")).astype(float)
    forward = close.shift(-1) / close - 1.0
    direction = regime.map({"BULL": 1.0, "BEAR": -1.0, "RANGE": 0.0})
    success = pd.Series(np.where(direction == 0, (forward.abs() <= volatility).astype(float), (np.sign(forward) == np.sign(direction)).astype(float)), index=close.index)
    quality = (0.55 * success + 0.45 * persistence).where(forward.notna())
    trust, _ = _rolling_trust(quality, maturity_horizon=1, minimum=max(8, min(20, window // 6)), window=min(240, max(60, window)))
    reliability = trust * 10.0
    uncertainty = 100.0 - reliability
    alpha = signal.clip(-1, 1) * 100.0
    beta = (volatility / volatility.rolling(window, min_periods=minimum).median()).clip(0, 3) * 33.3333
    delta = alpha.diff()
    return pd.DataFrame({
        f"{name} Regime": regime,
        f"{name} Alpha": alpha.round(3),
        f"{name} Beta": beta.round(3),
        f"{name} Delta": delta.round(3),
        f"{name} Regime Age": age,
        f"{name} Expected Duration": expected.round(2),
        f"{name} Expected Remaining Duration": remaining.round(2),
        f"{name} Transition Probability": transition.round(2),
        f"{name} Reliability": reliability.round(2),
        f"{name} Uncertainty": uncertainty.round(2),
        f"{name} Trust /10": trust,
        f"{name} Rank": _rank_labels(trust),
        f"{name} Data-Quality Status": np.where(mean.notna(), "LOCAL FALLBACK VALID", "INSUFFICIENT HISTORY"),
    })


def _published_or_fallback(work: pd.DataFrame, published_aliases: list[str], fallback: pd.Series) -> tuple[pd.Series, pd.Series]:
    column = _find_col(work, published_aliases)
    if column is None:
        return fallback, pd.Series("LOCAL_FALLBACK_RESEARCH", index=work.index, dtype="object")
    published = pd.to_numeric(work[column], errors="coerce")
    result = published.combine_first(fallback)
    source = pd.Series(np.where(published.notna(), "PUBLISHED", "LOCAL_FALLBACK_RESEARCH"), index=work.index, dtype="object")
    return result, source


def _decision_from_work(work: pd.DataFrame, prefix: str, aliases: list[str], fallback: pd.Series | None = None) -> tuple[pd.Series, pd.Series]:
    candidates = [f"__{prefix}_decision", *aliases]
    column = _find_col(work, candidates)
    if column:
        signal = work[column].astype("object")
    else:
        signal = pd.Series(pd.NA, index=work.index, dtype="object")
    if fallback is not None:
        signal = signal.combine_first(fallback)
    score_column = _find_col(work, [f"__{prefix}_score", f"{prefix} /10", f"{prefix}/10", f"{prefix} Score"])
    score = pd.to_numeric(work[score_column], errors="coerce") if score_column else pd.Series(np.nan, index=work.index)
    return signal, score


def _decision_trust(signal: pd.Series, score: pd.Series, close: pd.Series, returns: pd.Series) -> pd.Series:
    signed = signal.map(_direction).astype(float)
    future = close.shift(-1) / close - 1.0
    rolling_vol = returns.rolling(24, min_periods=8).std()
    success = pd.Series(np.where(signed == 0, future.abs() <= rolling_vol, np.sign(future) == np.sign(signed)), index=signal.index, dtype=float)
    success = success.where(future.notna())
    consistency = 1.0 - signed.diff().abs().clip(0, 2) / 2.0
    score_norm = pd.to_numeric(score, errors="coerce").clip(0, 10) / 10.0
    quality = (0.65 * success + 0.20 * consistency + 0.15 * score_norm.fillna(0.5)).where(success.notna())
    trust, _ = _rolling_trust(quality, maturity_horizon=1, minimum=12, window=120)
    return trust


def _build_signature(state: Mapping[str, Any], overall: pd.DataFrame, histories: Mapping[str, pd.DataFrame] | None, canonical: Mapping[str, Any]) -> str:
    time_column = _time_col(overall) if isinstance(overall, pd.DataFrame) else None
    latest = ""
    if time_column and not overall.empty:
        parsed = _utc_series(overall[time_column])
        latest = str(parsed.max()) if parsed.notna().any() else ""
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        clock = shared_broker_time_provider(state, frame=overall, canonical=canonical)
        shared_latest = str(clock.get("latest_completed_h1_utc") or "")
        broker_offset = str(clock.get("broker_offset_minutes") or "")
        clock_contract = str(clock.get("contract_version") or "")
    except Exception:
        shared_latest = broker_offset = clock_contract = ""
    parts = [
        str(_first(canonical.get("run_id"), canonical.get("canonical_calculation_id"), default="")),
        str(_first(canonical.get("generation_id"), canonical.get("calculation_generation"), default="")),
        latest, shared_latest, broker_offset, clock_contract,
        str(len(overall) if isinstance(overall, pd.DataFrame) else 0),
        "|".join(sorted((histories or {}).keys())), VERSION,
    ]
    return sha256("||".join(parts).encode("utf-8", "ignore")).hexdigest()


def build_unified_lunch_trust_history(
    state: Mapping[str, Any],
    canonical: Mapping[str, Any],
    overall: pd.DataFrame | None = None,
    factor_histories: Mapping[str, pd.DataFrame] | None = None,
    *,
    max_rows: int = 600,
) -> pd.DataFrame:
    """Build up to 600 completed-H1 rows across the latest 25 broker days."""
    overall = overall if isinstance(overall, pd.DataFrame) else pd.DataFrame()
    ohlc = _prepare_ohlc(state, canonical, overall)
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider
        clock = shared_broker_time_provider(state, frame=ohlc, canonical=canonical)
        cutoff_value = clock.get("latest_completed_h1_utc")
    except Exception:
        cutoff_value = _first(
            canonical.get("completed_broker_candle"), canonical.get("latest_completed_candle_time"),
            canonical.get("latest_completed_h1_utc"), default=None,
        )
    cutoff = pd.to_datetime(cutoff_value, errors="coerce", utc=True)
    if pd.notna(cutoff) and not ohlc.empty:
        ohlc = ohlc.loc[ohlc["time"] <= pd.Timestamp(cutoff).floor("h")]
    ohlc = _last_25_broker_days(ohlc, state, canonical, max_rows=max_rows)
    if ohlc.empty:
        columns = list(dict.fromkeys([*IDENTITY_COLUMNS, *PREDICTION_COLUMNS, *REGIME_COLUMNS, *[DECISION_RENAMES.get(c, c) for c in DECISION_COLUMNS]]))
        return pd.DataFrame(columns=columns)

    work = _merge_overall(ohlc, overall)
    work = _merge_factor_histories(work, factor_histories)
    close = pd.to_numeric(work["close"], errors="coerce")
    open_ = pd.to_numeric(work["open"], errors="coerce")
    high = pd.to_numeric(work["high"], errors="coerce")
    low = pd.to_numeric(work["low"], errors="coerce")
    returns = close.pct_change()
    previous_close = close.shift(1)
    true_range = pd.concat([(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(14, min_periods=5).mean()
    drift = returns.rolling(24, min_periods=8).mean().clip(-0.003, 0.003)
    mean_reversion = ((close - close.rolling(24, min_periods=8).mean()) / atr.replace(0, np.nan)).clip(-3, 3)

    result = pd.DataFrame(index=work.index)
    result["Completed Broker Candle"] = work["broker_time"]
    result["Broker Day"] = work["broker_time"].dt.strftime("%Y-%m-%d")
    result["Broker Hour"] = work["broker_time"].dt.strftime("%H:00")
    result["Symbol"] = str(_first(canonical.get("symbol"), default="EURUSD"))
    result["Timeframe"] = str(_first(canonical.get("timeframe"), default="H1"))
    result["Session"] = _session_from_hour(work["broker_time"].dt.hour)
    result["Run ID"] = str(_first(canonical.get("run_id"), canonical.get("canonical_calculation_id"), default="UNAVAILABLE"))
    result["Generation ID"] = str(_first(canonical.get("generation_id"), canonical.get("calculation_generation"), default="UNAVAILABLE"))
    result["Source Version"] = VERSION

    horizon_sources: list[pd.Series] = []
    forecast_values: dict[int, pd.Series] = {}
    actual_values: dict[int, pd.Series] = {}
    trust_values: dict[int, pd.Series] = {}
    for horizon in (1, 2, 3, 6):
        fallback = close * (1.0 + drift.fillna(0.0) * horizon)
        aliases = [
            f"H+{horizon} Predicted Price", f"Predicted {horizon}h Price", f"Predicted {horizon}H",
            f"Prediction H{horizon}", f"Forecast H{horizon}", f"h{horizon}",
        ]
        prediction, source = _published_or_fallback(work, aliases, fallback)
        actual = close.shift(-horizon)
        error = (prediction - actual).abs()
        normalized_error = error / atr.replace(0, np.nan)
        accuracy = np.exp(-normalized_error.clip(lower=0, upper=20))
        direction_hit = (np.sign(prediction - close) == np.sign(actual - close)).astype(float).where(actual.notna())
        trust, _ = _rolling_trust(accuracy, maturity_horizon=horizon, direction_hit=direction_hit, minimum=12, window=120)
        result[f"H+{horizon} Predicted Price"] = prediction.round(6)
        result[f"H+{horizon} Actual Matured Price"] = actual.round(6)
        result[f"H+{horizon} Error"] = error.round(6)
        result[f"H+{horizon} Trust /10"] = trust
        result[f"H+{horizon} Rank"] = _rank_labels(trust)
        forecast_values[horizon] = prediction
        actual_values[horizon] = actual
        trust_values[horizon] = trust
        horizon_sources.append(source)

    lower_fallback = close - atr * 1.15
    upper_fallback = close + atr * 1.15
    lower, lower_source = _published_or_fallback(work, ["Next-H1 Lower Bound", "Lower Bound", "Lower Band", "lower_bound", "p10"], lower_fallback)
    upper, upper_source = _published_or_fallback(work, ["Next-H1 Upper Bound", "Upper Bound", "Upper Band", "upper_bound", "p90"], upper_fallback)
    actual_h1 = actual_values[1]
    coverage = ((actual_h1 >= lower) & (actual_h1 <= upper)).astype(float).where(actual_h1.notna())
    interval_width = upper - lower
    width_quality = np.exp(-(interval_width / atr.replace(0, np.nan)).clip(lower=0, upper=20) / 3.0)
    interval_quality = (0.65 * coverage + 0.35 * width_quality).where(coverage.notna())
    interval_trust, _ = _rolling_trust(interval_quality, maturity_horizon=1, coverage=coverage, minimum=12, window=120)
    result["Next-H1 Lower Bound"] = lower.round(6)
    result["Next-H1 Upper Bound"] = upper.round(6)
    result["Interval Coverage"] = coverage.astype("Float64")
    result["Interval Width"] = interval_width.round(6)
    result["Interval Trust /10"] = interval_trust

    # Blue = trend-following path; Red = mean-reversion path when no published path exists.
    blue_fallback = forecast_values[3]
    red_fallback = close - mean_reversion.fillna(0.0) * atr * 0.30
    blue, blue_source = _published_or_fallback(work, ["Blue Path Value", "Blue Path", "blue_path", "Predicted Blue Path"], blue_fallback)
    red, red_source = _published_or_fallback(work, ["Red Path Value", "Red Path", "red_path", "Predicted Red Path"], red_fallback)
    blue_actual = actual_values[3]
    red_actual = actual_values[3]
    blue_accuracy = np.exp(-((blue - blue_actual).abs() / atr.replace(0, np.nan)).clip(0, 20))
    red_accuracy = np.exp(-((red - red_actual).abs() / atr.replace(0, np.nan)).clip(0, 20))
    blue_hit = (np.sign(blue - close) == np.sign(blue_actual - close)).astype(float).where(blue_actual.notna())
    red_hit = (np.sign(red - close) == np.sign(red_actual - close)).astype(float).where(red_actual.notna())
    blue_trust, _ = _rolling_trust(blue_accuracy, maturity_horizon=3, direction_hit=blue_hit, minimum=12, window=120)
    red_trust, _ = _rolling_trust(red_accuracy, maturity_horizon=3, direction_hit=red_hit, minimum=12, window=120)
    result["Blue Path Direction"] = _direction_text(blue, close)
    result["Blue Path Value"] = blue.round(6)
    result["Blue Path Trust /10"] = blue_trust
    result["Blue Path Rank"] = _rank_labels(blue_trust)
    result["Red Path Direction"] = _direction_text(red, close)
    result["Red Path Value"] = red.round(6)
    result["Red Path Trust /10"] = red_trust
    result["Red Path Rank"] = _rank_labels(red_trust)

    path_matrix = pd.concat([forecast_values[h] for h in (1, 2, 3, 6)], axis=1)
    direction_matrix = path_matrix.sub(close, axis=0).apply(np.sign)
    direction_agreement = direction_matrix.abs().sum(axis=1).where(direction_matrix.notna().any(axis=1))
    # 0 means evenly conflicted, 10 means all four horizons agree in one direction.
    signed_sum = direction_matrix.sum(axis=1).abs()
    result["Direction Agreement /10"] = (signed_sum / 4.0 * 10.0).round(3)
    path_change = path_matrix.pct_change(axis=1).std(axis=1)
    result["Path Stability /10"] = (10.0 * np.exp(-(path_change / returns.rolling(24, min_periods=8).std().replace(0, np.nan)).clip(0, 20))).round(3)
    result["Uncertainty %"] = (100.0 - pd.concat([*trust_values.values(), interval_trust], axis=1).mean(axis=1) * 10.0).clip(0, 100).round(2)
    vol_short = returns.rolling(12, min_periods=6).std()
    vol_long = returns.rolling(120, min_periods=24).std()
    change_score = (vol_short / vol_long.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    result["Changepoint Warning"] = np.select([change_score >= 1.8, change_score >= 1.35], ["HIGH", "WATCH"], default="STABLE")

    lower_regime = _regime_features(close, returns, 24, "Lower")
    middle_regime = _regime_features(close, returns, 120, "Middle")
    higher_regime = _regime_features(close, returns, min(600, max(120, len(close))), "Higher")
    for frame in (lower_regime, middle_regime, higher_regime):
        result = pd.concat([result, frame], axis=1)
    hierarchy = pd.concat([
        result["Lower Regime"], result["Middle Regime"], result["Higher Regime"]
    ], axis=1)
    agreement = hierarchy.apply(lambda row: 100.0 * row.dropna().value_counts(normalize=True).max() if len(row.dropna()) else np.nan, axis=1)
    for label in ("Lower", "Middle", "Higher"):
        result[f"{label} Hierarchy Agreement"] = agreement.round(2)

    # Local, deterministic decision fallbacks use completed H1 only.
    close_location = ((close - low) / (high - low).replace(0, np.nan)).clip(0, 1)
    positive_pressure = ((returns / returns.rolling(24, min_periods=8).std().replace(0, np.nan)).clip(-3, 3) + 3) / 6
    buy_pressure_value = (10.0 * (0.6 * positive_pressure + 0.4 * close_location)).clip(0, 10)
    sell_pressure_value = 10.0 - buy_pressure_value
    net_pressure_value = buy_pressure_value - sell_pressure_value
    fallback_direction = pd.Series(np.select([net_pressure_value.fillna(0) >= 1.5, net_pressure_value.fillna(0) <= -1.5], ["BUY", "SELL"], default="WAIT"), index=work.index, dtype="object")
    pullback_fallback = pd.Series(np.where(mean_reversion.abs().fillna(0) >= 1.25, "READY", "NOT READY"), index=work.index, dtype="object")
    uncertainty_numeric = pd.to_numeric(result["Uncertainty %"], errors="coerce").fillna(100.0)
    agreement_numeric = pd.to_numeric(result["Direction Agreement /10"], errors="coerce").fillna(0.0)
    hold_fallback = pd.Series(np.where((uncertainty_numeric <= 35) & fallback_direction.ne("WAIT"), "SAFE", "PROTECT"), index=work.index, dtype="object")
    tp_fallback = pd.Series(np.where((atr.fillna(0) > 0) & (agreement_numeric >= 5), "GOOD", "LOW"), index=work.index, dtype="object")
    direction_confirmation_fallback = pd.Series(np.where(agreement_numeric >= 7.5, fallback_direction, "WAIT"), index=work.index, dtype="object")
    entry_fallback = pd.Series(np.where((agreement_numeric >= 7.5) & (uncertainty_numeric <= 35), fallback_direction, "WAIT"), index=work.index, dtype="object")

    decision_specs = {
        "Entry": (["Entry Decision", "Entry Strength", "Entry"], entry_fallback),
        "Buy Pressure": (["Buy Pressure", "BUY Pressure", "BUY /10"], pd.Series(np.where(buy_pressure_value >= 6, "BUY", "WAIT"), index=work.index)),
        "Sell Pressure": (["Sell Pressure", "SELL Pressure", "SELL /10"], pd.Series(np.where(sell_pressure_value >= 6, "SELL", "WAIT"), index=work.index)),
        "Net Pressure": (["Net Pressure", "Pressure Decision"], fallback_direction),
        "Pullback": (["Pullback Readiness", "Pullback Decision"], pullback_fallback),
        # H1 cannot truthfully recreate M1 evidence. Keep it unavailable unless published.
        "M1": (["M1 Confirmation", "M1 Decision"], None),
        "Master Decision": (["Master Decision", "Final Decision", "Decision", "Production Decision Raw"], fallback_direction),
        "Hold Safety": (["Hold Safety", "Hold Safety Decision", "Hold/10"], hold_fallback),
        "TP Quality": (["TP Quality", "TP Quality Decision", "TP/10"], tp_fallback),
        "Direction Confirmation": (["Direction Confirmation", "Direction Confirmation Decision", "Direction"], direction_confirmation_fallback),
    }
    for prefix, (aliases, fallback) in decision_specs.items():
        signal, score = _decision_from_work(work, prefix, aliases, fallback)
        trust = _decision_trust(signal, score, close, returns)
        display_name = prefix if prefix.endswith("Decision") else DECISION_RENAMES.get(f"{prefix} Decision", f"{prefix} Decision")
        result[display_name] = signal
        result[f"{prefix} Trust /10"] = trust
        result[f"{prefix} Rank"] = _rank_labels(trust)

    original_column = _find_col(work, ["Production Decision Raw", "Final Decision", "Master Decision", "Decision", "Direction"])
    result["Original Production Direction"] = work[original_column].astype("object") if original_column else pd.Series(pd.NA, index=work.index, dtype="object")
    master = result["Master Decision"].map(_direction).fillna(0.0)
    master_trust = pd.to_numeric(result["Master Decision Trust /10"], errors="coerce").fillna(-1.0)
    uncertainty = pd.to_numeric(result["Uncertainty %"], errors="coerce").fillna(100.0)
    pullback_ready = result["Pullback Readiness"].astype(str).str.upper().str.contains("READY", na=False)
    action = np.select(
        [
            ((master_trust >= 7.5) & (uncertainty <= 30) & master.ne(0)).to_numpy(dtype=bool),
            (master.ne(0) & pullback_ready).to_numpy(dtype=bool),
            (master.ne(0) & (master_trust >= 5.0)).to_numpy(dtype=bool),
        ],
        ["ALLOWED", "WAIT FOR PULLBACK", "HOLD AND PROTECT"],
        default="NO TRADE",
    )
    result["Protective Action"] = pd.Series(action, index=result.index, dtype="object")
    result["Protective Reason"] = np.select(
        [
            result["Protective Action"].eq("ALLOWED"),
            result["Protective Action"].eq("WAIT FOR PULLBACK"),
            result["Protective Action"].eq("HOLD AND PROTECT"),
        ],
        [
            "Validated prior outcomes, aligned horizons and controlled uncertainty.",
            "Direction exists but price extension or pullback evidence advises patience.",
            "Direction remains partly supported, but uncertainty does not justify new exposure.",
        ],
        default="Evidence coverage, calibration or agreement is insufficient.",
    )

    # Source and quality diagnostics are calculated last from actual populated cells.
    source_matrix = pd.concat([*horizon_sources, lower_source, upper_source, blue_source, red_source], axis=1)
    fallback_any = source_matrix.eq("LOCAL_FALLBACK_RESEARCH").any(axis=1)
    published_any = source_matrix.eq("PUBLISHED").any(axis=1)
    result["Source"] = np.select([published_any & fallback_any, published_any], ["MIXED PUBLISHED + LOCAL FALLBACK", "PUBLISHED"], default="LOCAL FALLBACK RESEARCH")
    required_quality_columns = [
        "Blue Path Value", "Red Path Value", "H+1 Predicted Price", "H+3 Predicted Price", "H+6 Predicted Price",
        "Lower Regime", "Middle Regime", "Higher Regime", "Master Decision", "Hold Safety", "TP Quality",
        "Direction Confirmation",
    ]
    available = result[required_quality_columns].notna().sum(axis=1)
    result["Data Coverage %"] = (available / len(required_quality_columns) * 100.0).round(2)
    result["Data-Quality Status"] = np.select(
        [result["Data Coverage %"] >= 85, result["Data Coverage %"] >= 60],
        ["VALID", "PARTIAL"], default="INSUFFICIENT",
    )
    result["Missingness Reason"] = np.where(
        result["Data Coverage %"] >= 100,
        "",
        "One or more published components were unavailable; only completed-candle local fallback values were used where permitted. M1 remains missing unless published.",
    )
    matured_counts = pd.concat([actual_values[h].notna() for h in (1, 2, 3, 6)], axis=1).sum(axis=1)
    result["Validation Status"] = np.select(
        [matured_counts == 4, matured_counts > 0], ["MATURED", "PARTIALLY MATURED"], default="PENDING OUTCOMES"
    )

    # Enforce vocabulary and deterministic output order.
    result["Protective Action"] = result["Protective Action"].where(result["Protective Action"].isin(ALLOWED_PROTECTIVE_ACTIONS), "NO TRADE")
    ordered = list(dict.fromkeys([
        *IDENTITY_COLUMNS, *PREDICTION_COLUMNS, *REGIME_COLUMNS,
        *[DECISION_RENAMES.get(c, c) for c in DECISION_COLUMNS],
    ]))
    for column in ordered:
        if column not in result.columns:
            result[column] = pd.NA
    result = result[ordered].sort_values("Completed Broker Candle", ascending=False, kind="mergesort").reset_index(drop=True)
    result.attrs.update({
        "version": VERSION,
        "production_values_modified": False,
        "table3_modified": False,
        "full_h1_rows": int(len(result)),
        "broker_days": int(result["Broker Day"].nunique(dropna=True)),
        "fallback_is_research_only": True,
    })
    return result


def get_or_build_unified_history(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any],
    overall: pd.DataFrame,
    factor_histories: Mapping[str, pd.DataFrame] | None,
) -> pd.DataFrame:
    signature = _build_signature(state, overall, factor_histories, canonical)
    cached = state.get(CACHE_KEY)
    if isinstance(cached, Mapping) and cached.get("signature") == signature and isinstance(cached.get("frame"), pd.DataFrame):
        return cached["frame"]
    frame = build_unified_lunch_trust_history(state, canonical, overall, factor_histories)
    state[CACHE_KEY] = {"signature": signature, "frame": frame}
    state[FRAME_KEY] = frame
    return frame


def _daily_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    numeric_trust = [column for column in frame.columns if column.endswith("Trust /10")]
    aggregations: dict[str, Any] = {
        "Completed Broker Candle": "max", "Protective Action": "first",
        "Original Production Direction": "first", "Data Coverage %": "mean",
        "Data-Quality Status": "first", "Master Decision": "first",
    }
    for column in numeric_trust:
        aggregations[column] = "mean"
    summary = frame.sort_values("Completed Broker Candle", ascending=False).groupby("Broker Day", as_index=False).agg(aggregations)
    return summary.sort_values("Completed Broker Candle", ascending=False).head(25).reset_index(drop=True)


def render_unified_lunch_trust_history(
    state: MutableMapping[str, Any],
    canonical: Mapping[str, Any],
    overall: pd.DataFrame,
    factor_histories: Mapping[str, pd.DataFrame] | None,
) -> pd.DataFrame:
    """Render a bounded view while preserving full 25-day H1 export data."""
    import streamlit as st

    frame = get_or_build_unified_history(state, canonical, overall, factor_histories)
    st.markdown("#### Table 2 — Unified Lunch Trust and Decision History — Last 25 Broker Days")
    st.caption(
        "Up to 600 completed H1 rows across the latest 25 broker days. Trust is based on matured historical outcomes; "
        "local fallback calculations are labelled research-only and never overwrite production values or Table 3."
    )
    if frame.empty:
        st.dataframe(frame, use_container_width=True, hide_index=True, height=260)
        st.info("No completed-candle market history is available. Missing values were not fabricated.")
        return frame

    mobile = bool(state.get("extreme_mobile_lite_mode_20260628") or state.get("phone_mode"))
    if mobile:
        view_mode = st.radio("Mobile history view", ["Latest H1 rows", "25-day summary"], horizontal=True, key="trust_history_mobile_view_20260628")
        source = _daily_summary(frame) if view_mode == "25-day summary" else frame
        groups = list(COLUMN_GROUPS)
        with st.form("trust_history_mobile_controls_20260628"):
            group = st.selectbox("Column group", groups, index=0)
            page_size = st.selectbox("Rows per page", [10, 25], index=0)
            max_page = max(1, math.ceil(len(source) / int(page_size)))
            page = st.number_input("Page", min_value=1, max_value=max_page, value=min(int(state.get("trust_history_mobile_page_20260628", 1)), max_page), step=1)
            submitted = st.form_submit_button("Apply view")
        if submitted:
            state["trust_history_mobile_page_20260628"] = int(page)
        columns = [column for column in COLUMN_GROUPS[group] if column in source.columns]
        start = (int(page) - 1) * int(page_size)
        view = source.iloc[start:start + int(page_size)][columns]
        st.dataframe(view, use_container_width=True, hide_index=True, height=min(460, 82 + 34 * max(1, len(view))))
        st.caption(f"Showing {start + 1:,}–{min(start + int(page_size), len(source)):,} of {len(source):,} rows. Only the selected page and columns are rendered.")
    else:
        with st.form("trust_history_desktop_controls_20260628"):
            group = st.selectbox("Table 2 column group", ["All", *COLUMN_GROUPS], index=0)
            page_size = st.selectbox("Rows per page", [25, 50, 100], index=1)
            max_page = max(1, math.ceil(len(frame) / int(page_size)))
            page = st.number_input("Page", min_value=1, max_value=max_page, value=1, step=1)
            st.form_submit_button("Apply table view")
        columns = list(frame.columns) if group == "All" else [column for column in COLUMN_GROUPS[group] if column in frame.columns]
        start = (int(page) - 1) * int(page_size)
        view = frame.iloc[start:start + int(page_size)][columns]
        st.dataframe(view, use_container_width=True, hide_index=True, height=520)
        st.caption(f"Showing {start + 1:,}–{min(start + int(page_size), len(frame)):,} of {len(frame):,} H1 rows.")

    export_cols = st.columns(2)
    export_cols[0].download_button(
        "Download Complete 25-Day CSV",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="unified_lunch_trust_history_last_25_broker_days.csv",
        mime="text/csv",
        key="unified_trust_history_full_export_20260628",
        use_container_width=True,
    )
    export_cols[1].download_button(
        "Download 25-Day Summary CSV",
        _daily_summary(frame).to_csv(index=False).encode("utf-8"),
        file_name="unified_lunch_trust_daily_summary.csv",
        mime="text/csv",
        key="unified_trust_history_daily_export_20260628",
        use_container_width=True,
    )
    return frame


__all__ = [
    "VERSION", "CACHE_KEY", "FRAME_KEY", "ALLOWED_PROTECTIVE_ACTIONS",
    "build_unified_lunch_trust_history", "get_or_build_unified_history",
    "render_unified_lunch_trust_history", "COLUMN_GROUPS",
]
