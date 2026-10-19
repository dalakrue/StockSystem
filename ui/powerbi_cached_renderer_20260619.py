"""Cached-only Power BI Price Prediction Projection renderer.

The Settings orchestrator remains the sole owner of prediction/calibration work.
This renderer intentionally contains no model, calibration, OHLC preprocessing,
or shared-calculation call.  It reads the atomically published cache and uses a
Streamlit fragment so chart controls rerun only this display.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Iterable, Mapping, MutableMapping

import numpy as np
import pandas as pd
import streamlit as st

from core.scalar_normalization_20260625 import metric_text, normalize_scalar

_FRAGMENT = getattr(st, "fragment", lambda fn: fn)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def _selected_forecast(canonical: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
    final = _mapping(canonical.get("final_decision"))
    forecasts = _mapping(canonical.get("forecasts"))
    horizon = int(_finite(final.get("selected_horizon"), _finite(forecasts.get("selected_horizon"), 3.0)) or 3)
    return horizon, _mapping(_mapping(forecasts.get("horizons")).get(f"{horizon}h"))


def _frame_latest_time(frame: pd.DataFrame) -> pd.Timestamp | None:
    """Return the newest timestamp without changing the protected dataframe."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {str(c).strip().lower().replace("_", " "): c for c in frame.columns}
    column = None
    for alias in ("time", "datetime", "timestamp", "date", "future time", "target time", "projection time"):
        key = alias.replace("_", " ")
        if key in normalized:
            column = normalized[key]
            break
    if column is None:
        return None
    parsed = pd.to_datetime(frame[column], errors="coerce", utc=True)
    valid = parsed.dropna()
    return pd.Timestamp(valid.max()) if not valid.empty else None


def _first_dataframe(state: Mapping[str, Any], keys: Iterable[str]) -> pd.DataFrame:
    """Choose the freshest usable cache instead of the first stale alias."""
    candidates: list[tuple[pd.Timestamp, int, pd.DataFrame]] = []
    fallback: list[tuple[int, pd.DataFrame]] = []
    for priority, key in enumerate(keys):
        value = state.get(key)
        if not isinstance(value, pd.DataFrame) or value.empty:
            continue
        fallback.append((priority, value))
        latest = _frame_latest_time(value)
        if latest is not None:
            candidates.append((latest, -priority, value))
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[2]
    return min(fallback, key=lambda item: item[0])[1] if fallback else pd.DataFrame()


def _plot_clock(values: Any, state: Mapping[str, Any] | None = None) -> Any:
    """Project UTC candle identity to the one shared MetaTrader broker clock.

    Plotly/browser timezone handling must never move Field 2 to a different hour
    from Field 1. The timestamp remains UTC in calculation storage; only this
    display projection removes timezone metadata after applying the validated
    broker offset.
    """
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    state_map: Mapping[str, Any] = state if isinstance(state, Mapping) else st.session_state
    tzinfo = timezone.utc
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider

        contract = shared_broker_time_provider(state_map)
        minutes = contract.get("broker_offset_minutes")
        if minutes is not None:
            tzinfo = timezone(timedelta(minutes=int(minutes)))
    except Exception:
        # UTC is an explicit fail-safe display only when no validated broker
        # offset exists; it never changes calculation/candle identity.
        tzinfo = timezone.utc
    if isinstance(parsed, pd.Series):
        return parsed.dt.tz_convert(tzinfo).dt.tz_localize(None)
    if isinstance(parsed, pd.DatetimeIndex):
        return parsed.tz_convert(tzinfo).tz_localize(None)
    if pd.isna(parsed):
        return parsed
    stamp = pd.Timestamp(parsed)
    return stamp.tz_convert(tzinfo).tz_localize(None) if stamp.tzinfo is not None else stamp


def _broker_display_table(
    frame: pd.DataFrame,
    state: Mapping[str, Any],
    canonical: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return a display-only table with every visible clock alias synchronized."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    try:
        from core.shared_broker_time_20260622 import frame_to_shared_broker_clock

        return frame_to_shared_broker_clock(
            frame, state, canonical=canonical, reject_future_incomplete=False
        )
    except Exception:
        return frame


def _shared_broker_candle_label(
    state: Mapping[str, Any],
    canonical: Mapping[str, Any],
    frame: pd.DataFrame | None = None,
) -> str:
    """Use the same last-completed-H1 label as all Lunch identity surfaces."""
    try:
        from core.shared_broker_time_20260622 import shared_broker_time_provider

        contract = shared_broker_time_provider(state, frame=frame, canonical=canonical)
        return str(contract.get("shared_broker_time_display") or "Not available")
    except Exception:
        return str(canonical.get("latest_completed_candle_time") or "Not available")


def _column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    normalized = {str(c).strip().lower().replace("_", " "): str(c) for c in frame.columns}
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        if key in normalized:
            return normalized[key]
    for alias in aliases:
        key = str(alias).strip().lower().replace("_", " ")
        for normalized_name, original in normalized.items():
            if key and key in normalized_name:
                return original
    return None


def _market_view(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    t = _column(frame, ("time", "datetime", "timestamp", "date"))
    c = _column(frame, ("close", "c"))
    if t is None or c is None:
        return pd.DataFrame()
    o = _column(frame, ("open", "o"))
    h = _column(frame, ("high", "h"))
    l = _column(frame, ("low", "l"))
    out = pd.DataFrame({
        "time": pd.to_datetime(frame[t], errors="coerce", utc=True),
        "close": pd.to_numeric(frame[c], errors="coerce"),
    })
    out["open"] = pd.to_numeric(frame[o], errors="coerce") if o else out["close"]
    out["high"] = pd.to_numeric(frame[h], errors="coerce") if h else out[["open", "close"]].max(axis=1)
    out["low"] = pd.to_numeric(frame[l], errors="coerce") if l else out[["open", "close"]].min(axis=1)
    out = out.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last")
    if out.empty:
        return out
    out["high"] = out[["open", "high", "close"]].max(axis=1)
    out["low"] = out[["open", "low", "close"]].min(axis=1)
    return out.reset_index(drop=True)


def _path_frame(value: Any, value_aliases: Iterable[str]) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return pd.DataFrame()
    t = _column(value, ("time", "future time", "datetime", "timestamp", "date", "projection time"))
    p = _column(value, value_aliases)
    if t is None or p is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        "time": pd.to_datetime(value[t], errors="coerce", utc=True),
        "path": pd.to_numeric(value[p], errors="coerce"),
    }).dropna(subset=["time", "path"])
    return out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def _canonical_identity(state: MutableMapping[str, Any]) -> Mapping[str, Any]:
    from core.canonical_lookup_20260626 import resolve_canonical
    return resolve_canonical(state)


def _powerbi_error_context(state: Mapping[str, Any], bundle: Mapping[str, Any]) -> list[str]:
    messages: list[str] = []
    if bundle.get("message"):
        messages.append(str(bundle.get("message")))
    status = _mapping(state.get("settings_run_status_20260617"))
    powerbi = _mapping(status.get("powerbi"))
    if powerbi.get("message"):
        messages.append(str(powerbi.get("message")))
    for item in status.get("errors") or []:
        if "powerbi" in str(item).lower() or "projection" in str(item).lower():
            messages.append(str(item))
    try:
        from core.operational_sync_20260618 import errors_frame
        errors = errors_frame(state)
        if isinstance(errors, pd.DataFrame) and not errors.empty:
            component_col = _column(errors, ("component",))
            message_col = _column(errors, ("message", "error"))
            if component_col and message_col:
                mask = errors[component_col].astype(str).str.contains("powerbi|projection", case=False, regex=True, na=False)
                messages.extend(errors.loc[mask, message_col].astype(str).head(5).tolist())
    except Exception:
        # Diagnostics are optional; the primary stored failure remains visible.
        pass
    return list(dict.fromkeys(m for m in messages if m))




def _canonical_cutoff(canonical: Mapping[str, Any]) -> pd.Timestamp | None:
    raw = next((
        canonical.get(key) for key in (
            "completed_broker_candle", "broker_candle_time", "latest_completed_candle_time",
            "latest_completed_candle", "completed_candle", "canonical_completed_candle",
        ) if canonical.get(key) not in (None, "")
    ), None)
    parsed = pd.to_datetime(raw, errors="coerce", utc=True)
    return None if pd.isna(parsed) else pd.Timestamp(parsed)


def _select_market_for_canonical(
    state: Mapping[str, Any], canonical: Mapping[str, Any], child_bundle: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Select an exact-candle active-child OHLC frame, never a merely fresher alias."""
    candidates: list[tuple[str, pd.DataFrame]] = []
    child = child_bundle if isinstance(child_bundle, Mapping) else {}
    historical = child.get("historical_input_path")
    if isinstance(historical, list) and historical:
        candidates.append(("powerbi_child_bundle_20260706.historical_input_path", pd.DataFrame(historical)))
    current = child.get("current_candle")
    if isinstance(current, Mapping) and current:
        candidates.append(("powerbi_child_bundle_20260706.current_candle", pd.DataFrame([dict(current)])))
    for key in (
        "canonical_completed_ohlc_df_20260617", "calculation_staging_ohlc_df_20260617",
        "lunch_5layer_powerbi_df", "dv_pp_df", "last_df",
    ):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            candidates.append((key, value))
    cutoff = _canonical_cutoff(canonical)
    fallback: tuple[pd.DataFrame, list[str]] | None = None
    for source, raw in candidates:
        market = _market_view(raw)
        if market.empty:
            continue
        trimmed, notes = _trim_market_to_canonical_candle(market, canonical)
        if trimmed.empty:
            continue
        if fallback is None:
            fallback = (trimmed, [*notes, f"OHLC source: {source}"])
        latest = pd.to_datetime(trimmed["time"], errors="coerce", utc=True).dropna().max()
        if cutoff is None or (pd.notna(latest) and pd.Timestamp(latest) == cutoff):
            return trimmed, [*notes, f"OHLC source: {source} (exact canonical candle)"]
    return fallback if fallback is not None else (pd.DataFrame(), [])


def _latest_market_point(market: pd.DataFrame) -> tuple[pd.Timestamp | None, float | None]:
    """Return latest completed candle time/close from the same market frame used by Lunch.

    Display-only cache fragments can contain an anchor row or one stale row from
    the previous generation.  The renderer must not replace data silently, but it
    can discard non-future display rows and keep the latest completed candle as
    the single authority for Field 1 and Field 2.
    """
    if not isinstance(market, pd.DataFrame) or market.empty or "time" not in market or "close" not in market:
        return None, None
    ordered = market.dropna(subset=["time", "close"]).sort_values("time")
    if ordered.empty:
        return None, None
    return pd.Timestamp(ordered["time"].iloc[-1]), float(ordered["close"].iloc[-1])


def _filter_strict_future(frame: pd.DataFrame, latest: pd.Timestamp | None) -> pd.DataFrame:
    """Display-only filter: remove anchor/current/stale rows before validation/charting."""
    if latest is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    t = _column(frame, ("time", "future time", "datetime", "timestamp", "date", "projection time", "target time"))
    if not t:
        return frame
    out = frame.copy(deep=False)
    times = pd.to_datetime(out[t], errors="coerce", utc=True)
    out = out.loc[times.notna() & (times > latest)].copy()
    return out.reset_index(drop=True)


def _aligned_powerbi_inputs(
    market: pd.DataFrame,
    bundle: Mapping[str, Any],
    future_candles: pd.DataFrame,
) -> tuple[Mapping[str, Any], pd.DataFrame, list[str]]:
    """Keep Field 2 synchronized to the latest completed H1 candle.

    This does not run a model and does not fabricate forecasts.  It only removes
    non-future display rows from already-published caches and replaces a stale
    summary anchor with the current completed close when the path itself is now
    future-only.  The correction is shown in a caption, not hidden.
    """
    latest, close = _latest_market_point(market)
    notes: list[str] = []
    if latest is None:
        return bundle, future_candles, notes
    out = dict(bundle) if isinstance(bundle, Mapping) else {}
    main = out.get("main") if isinstance(out.get("main"), pd.DataFrame) else pd.DataFrame()
    filtered_main = _filter_strict_future(main, latest)
    if isinstance(main, pd.DataFrame) and len(filtered_main) != len(main):
        notes.append(f"Removed {len(main) - len(filtered_main)} non-future cached Power BI display row(s) so the path starts after {latest.isoformat()}.")
        out["main"] = filtered_main
    filtered_candles = _filter_strict_future(future_candles, latest)
    if isinstance(future_candles, pd.DataFrame) and len(filtered_candles) != len(future_candles):
        notes.append(f"Removed {len(future_candles) - len(filtered_candles)} non-future blue candle row(s).")
    summary = dict(_mapping(out.get("summary")))
    if close is not None:
        old_anchor = _finite(summary.get("anchor_price"))
        if old_anchor is not None and abs(old_anchor - close) > max(abs(close) * 1e-8, 1e-8):
            summary["anchor_price"] = close
            summary["anchor_time"] = latest.isoformat()
            notes.append("Aligned display anchor to the latest completed candle close used by Lunch Field 1.")
        out["summary"] = summary
    return out, filtered_candles, notes

def evaluate_projection_integrity(
    state: Mapping[str, Any],
    market: pd.DataFrame,
    bundle: Mapping[str, Any],
    future_candles: pd.DataFrame,
    canonical: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one exact-run production projection without creating a fallback."""
    from core.canonical_identity_20260627 import (
        CanonicalIntegrityError, ProjectionState, build_canonical_identity,
        identity_mismatches,
    )

    canonical = canonical or _canonical_identity(dict(state))
    try:
        identity = build_canonical_identity(canonical, state=state, require_complete=True)
    except CanonicalIntegrityError as exc:
        text = str(exc)
        state_code = ProjectionState.INVALID_TIMESTAMP if "candle" in text or "H1" in text else ProjectionState.PUBLICATION_INCOMPLETE
        return {"state": state_code.value, "valid": False, "issues": [text], "identity": None}

    if not isinstance(market, pd.DataFrame) or market.empty:
        return {
            "state": ProjectionState.INSUFFICIENT_DATA.value, "valid": False,
            "issues": ["Cached completed OHLC data is missing or has no usable time/close columns."],
            "identity": identity.as_dict(),
        }
    latest = pd.Timestamp(market["time"].iloc[-1])
    latest = latest.tz_localize("UTC") if latest.tzinfo is None else latest.tz_convert("UTC")
    if latest != identity.completed_broker_candle:
        return {
            "state": ProjectionState.STALE.value, "valid": False,
            "issues": [
                "Power BI OHLC latest completed H1 candle does not exactly match the canonical completed broker candle.",
                f"Power BI OHLC: {latest.isoformat()}",
                f"Canonical: {identity.completed_broker_candle.isoformat()}",
            ],
            "identity": identity.as_dict(),
        }

    mismatches = identity_mismatches(bundle, identity)
    if mismatches:
        incomplete = all("missing" in item for item in mismatches)
        code = ProjectionState.PUBLICATION_INCOMPLETE if incomplete else ProjectionState.IDENTITY_MISMATCH
        return {"state": code.value, "valid": False, "issues": mismatches, "identity": identity.as_dict()}

    main = bundle.get("main") if isinstance(bundle.get("main"), pd.DataFrame) else pd.DataFrame()
    summary = _mapping(bundle.get("summary"))
    issues: list[str] = []
    if main.empty:
        return {
            "state": ProjectionState.PATH_UNAVAILABLE.value, "valid": False,
            "issues": ["The exact-run production central path was not published."],
            "identity": identity.as_dict(),
        }
    future_times = pd.to_datetime(main.get("time"), errors="coerce", utc=True) if "time" in main else pd.Series(dtype="datetime64[ns, UTC]")
    if future_times.empty or future_times.isna().any() or not bool((future_times > latest).all()):
        issues.append("Power BI future timestamps are not strictly after the latest completed H1 candle.")
    anchor_price = summary.get("anchor_price")
    if anchor_price not in (None, ""):
        try:
            tolerance = max(abs(float(market["close"].iloc[-1])) * 1e-8, 1e-8)
            if abs(float(anchor_price) - float(market["close"].iloc[-1])) > tolerance:
                issues.append("Projection anchor does not match the latest completed close.")
        except Exception:
            issues.append("Projection anchor is not a valid number.")
    if isinstance(future_candles, pd.DataFrame) and not future_candles.empty:
        t = _column(future_candles, ("time", "datetime", "timestamp"))
        if t:
            times = pd.to_datetime(future_candles[t], errors="coerce", utc=True)
            if times.isna().any() or not bool((times > latest).all()):
                issues.append("Cached blue future candles contain a non-future timestamp.")
    return {
        "state": (ProjectionState.VALID if not issues else ProjectionState.PUBLICATION_INCOMPLETE).value,
        "valid": not issues, "issues": issues, "identity": identity.as_dict(),
    }


def _validation(
    market: pd.DataFrame,
    main: pd.DataFrame,
    future_candles: pd.DataFrame,
    summary: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Backward-compatible pure validation wrapper used by legacy tests."""
    bundle = {"main": main, "summary": dict(summary)}
    # Bind supplied legacy pieces to the canonical identity only for this pure
    # compatibility wrapper. The live renderer validates the stored publication.
    for target in (bundle, bundle["summary"]):
        for key, aliases in {
            "run_id": ("run_id", "canonical_calculation_id"),
            "generation_id": ("generation_id", "calculation_generation"),
            "symbol": ("symbol",), "timeframe": ("timeframe",),
            "source_snapshot_hash": ("source_snapshot_hash", "snapshot_hash"),
            "source_signature": ("source_signature",),
            "completed_broker_candle": ("completed_broker_candle", "broker_candle_time", "latest_completed_candle_time"),
        }.items():
            for alias in aliases:
                if canonical.get(alias) not in (None, ""):
                    target.setdefault(key, canonical.get(alias)); break
    result = evaluate_projection_integrity({}, market, bundle, future_candles, canonical)
    return bool(result["valid"]), list(result["issues"])


def _historical_paths(frame: pd.DataFrame, latest: pd.Timestamp, max_paths: int = 6) -> list[pd.DataFrame]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    t = _column(frame, ("time", "future time", "target time", "projection time", "datetime", "timestamp"))
    p = _column(frame, ("predicted close", "pred close", "projected close", "forecast close", "path", "close"))
    if t is None or p is None:
        return []
    group = _column(frame, ("origin time", "forecast time", "run id", "calculation id", "projection id", "anchor time"))
    work = frame.copy(deep=False)
    work = work.assign(
        __time=pd.to_datetime(work[t], errors="coerce", utc=True),
        __path=pd.to_numeric(work[p], errors="coerce"),
    ).dropna(subset=["__time", "__path"])
    work = work.loc[work["__time"] <= latest + pd.Timedelta(days=8)]
    if work.empty:
        return []
    def display_aggregate(path: pd.DataFrame, limit: int) -> pd.DataFrame:
        # M4 is display-only: raw projection history remains untouched for every
        # statistic, settlement and export. First/last/min/max are preserved per
        # visual bucket before Plotly serialization.
        if len(path) <= limit:
            return path.reset_index(drop=True)
        from core.research_evidence_algorithms_20260620 import m4_downsample
        return m4_downsample(path, x_col="time", y_col="path", max_points=limit)

    if group is None:
        path = work[["__time", "__path"]].rename(columns={"__time": "time", "__path": "path"}).sort_values("time")
        return [display_aggregate(path, 80)]
    grouped: list[pd.DataFrame] = []
    for _, item in list(work.groupby(group, sort=False))[-max_paths:]:
        path = item[["__time", "__path"]].rename(columns={"__time": "time", "__path": "path"}).sort_values("time")
        if not path.empty:
            grouped.append(display_aggregate(path, 48))
    return grouped


def _regime_alpha_delta(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> tuple[Any, Any]:
    regime = _mapping(canonical.get("regime"))
    alpha = regime.get("alpha")
    delta = regime.get("delta")
    if alpha in (None, "") or delta in (None, ""):
        analytics = _mapping(state.get("regime_window_analytics_20260618"))
        latest = _mapping(analytics.get("latest"))
        alpha = latest.get("alpha", alpha)
        delta = latest.get("delta", delta)
    return alpha if alpha not in (None, "") else "-", delta if delta not in (None, "") else "-"



def _validation_metrics(
    bt_history: pd.DataFrame,
    bt_summary: Mapping[str, Any],
    bundle_summary: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    direction = bt_summary.get("causal_actionable_direction_accuracy_pct", bt_summary.get("direction_accuracy_pct", "Unavailable"))
    balanced_direction = bt_summary.get("balanced_direction_accuracy_pct", "Unavailable")
    actionable_coverage = bt_summary.get("actionable_coverage_pct", "Unavailable")
    direction_status = bt_summary.get("direction_evidence_status", "LEGACY")
    median_error: Any = "Unavailable"
    rolling_skill: Any = "Unavailable"
    previous_skill: Any = "Unavailable"
    if isinstance(bt_history, pd.DataFrame) and not bt_history.empty:
        error_col = _column(bt_history, ("absolute error", "abs error", "absolute close error", "close error", "error"))
        if error_col:
            values = pd.to_numeric(bt_history[error_col], errors="coerce").dropna()
            if not values.empty:
                median_error = round(float(values.median()), 6)
        predicted_col = _column(bt_history, ("predicted close", "prediction", "forecast close"))
        actual_col = _column(bt_history, ("actual close", "actual"))
        rolling_col = _column(bt_history, ("rolling mean", "rolling forecast", "naive rolling"))
        previous_col = _column(bt_history, ("previous close", "naive previous", "last close"))
        if predicted_col and actual_col:
            predicted = pd.to_numeric(bt_history[predicted_col], errors="coerce")
            actual = pd.to_numeric(bt_history[actual_col], errors="coerce")
            model_mae = (predicted - actual).abs().mean()
            if rolling_col:
                baseline = (pd.to_numeric(bt_history[rolling_col], errors="coerce") - actual).abs().mean()
                if pd.notna(model_mae) and pd.notna(baseline) and baseline > 0:
                    rolling_skill = round(float(1.0 - model_mae / baseline) * 100.0, 2)
            if previous_col:
                baseline = (pd.to_numeric(bt_history[previous_col], errors="coerce") - actual).abs().mean()
                if pd.notna(model_mae) and pd.notna(baseline) and baseline > 0:
                    previous_skill = round(float(1.0 - model_mae / baseline) * 100.0, 2)
    regime = _mapping(canonical.get("regime"))
    reliability = next((value for value in (
        regime.get("reliability"), regime.get("regime_reliability"),
        regime.get("reliability_pct"), canonical.get("regime_reliability"),
        canonical.get("current_regime_reliability"), bundle_summary.get("regime_reliability"),
        bundle_summary.get("reliability_pct"),
    ) if value not in (None, "", "Unavailable")), "Insufficient settled regime evidence")
    created = pd.to_datetime(
        canonical.get("created_at") or canonical.get("forecast_created_at") or
        canonical.get("latest_completed_candle_time") or bundle_summary.get("anchor_time"),
        errors="coerce", utc=True
    )
    age = "Insufficient timestamp evidence"
    if pd.notna(created):
        hours = max(0.0, (pd.Timestamp.now(tz="UTC") - pd.Timestamp(created)).total_seconds() / 3600.0)
        age = f"{hours:.2f} h"
    return {
        "Causal Actionable Accuracy": f"{direction}%" if direction not in (None, "", "Unavailable") else "Unavailable",
        "Balanced Direction Accuracy": f"{balanced_direction}%" if balanced_direction not in (None, "", "Unavailable") else "Unavailable",
        "Actionable Forecast Coverage": f"{actionable_coverage}%" if actionable_coverage not in (None, "", "Unavailable") else "Unavailable",
        "Direction Evidence Status": direction_status,
        "Median Absolute Error": median_error,
        "80% Band Coverage": (f"{float(bundle_summary.get('estimated_band_coverage_pct')):.1f}%" if _finite(bundle_summary.get('estimated_band_coverage_pct')) is not None else "Insufficient settled interval outcomes"),
        "Skill vs Rolling Mean": f"{rolling_skill:+.2f}%" if isinstance(rolling_skill, (int, float)) else rolling_skill,
        "Skill vs Previous Close": f"{previous_skill:+.2f}%" if isinstance(previous_skill, (int, float)) else previous_skill,
        "Current Regime Reliability": reliability,
        "Forecast Age": age,
    }



def _probability_fallbacks(main: pd.DataFrame, market: pd.DataFrame, selected_forecast: Mapping[str, Any], final: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Calibrated display probabilities without degenerate 0%/100% cards.

    Explicit published probabilities are preferred. When absent, infer a normal
    probability from the published central endpoint and its 80% interval. This
    uses only the saved forecast generation and does not recalculate the model.
    """
    above = _finite(selected_forecast.get("buy_probability_calibrated"), _finite(selected_forecast.get("probability_above_current"), _finite(final.get("buy_probability"))))
    below = _finite(selected_forecast.get("sell_probability_calibrated"), _finite(selected_forecast.get("probability_below_current"), _finite(final.get("sell_probability"))))
    if above is not None and above > 1.0:
        above /= 100.0
    if below is not None and below > 1.0:
        below /= 100.0

    current = _finite(market["close"].iloc[-1]) if isinstance(market, pd.DataFrame) and not market.empty and "close" in market else None
    if (above is None or below is None) and current is not None and isinstance(main, pd.DataFrame) and not main.empty:
        main_col = _column(main, ("main path", "main_path", "predicted close", "forecast close", "path"))
        lower_col = _column(main, ("lower", "lower band", "lower_bound", "p10"))
        upper_col = _column(main, ("upper", "upper band", "upper_bound", "p90"))
        central = _finite(pd.to_numeric(main[main_col], errors="coerce").dropna().iloc[-1]) if main_col and not pd.to_numeric(main[main_col], errors="coerce").dropna().empty else None
        lower = _finite(pd.to_numeric(main[lower_col], errors="coerce").dropna().iloc[-1]) if lower_col and not pd.to_numeric(main[lower_col], errors="coerce").dropna().empty else None
        upper = _finite(pd.to_numeric(main[upper_col], errors="coerce").dropna().iloc[-1]) if upper_col and not pd.to_numeric(main[upper_col], errors="coerce").dropna().empty else None
        if central is not None and lower is not None and upper is not None and upper > lower:
            # For an 80% central interval, z ~= 1.28155.
            sigma = max((upper - lower) / (2.0 * 1.2815515655446004), 1e-8)
            z = (central - current) / sigma
            inferred = 0.5 * (1.0 + float(np.math.erf(z / np.sqrt(2.0)))) if hasattr(np, "math") else None
            if inferred is None:
                import math
                inferred = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            above = inferred if above is None else above
            below = 1.0 - inferred if below is None else below

    if above is not None and below is None:
        below = 1.0 - above
    if below is not None and above is None:
        above = 1.0 - below
    if above is not None and below is not None:
        total = above + below
        if total > 0:
            above, below = above / total, below / total
        # Finite-sample probability floor avoids misleading impossible certainty.
        above = float(np.clip(above, 0.005, 0.995))
        below = float(np.clip(below, 0.005, 0.995))
        total = above + below
        above, below = above / total, below / total
    return above, below


def _touch_probability_fallbacks(main: pd.DataFrame, market: pd.DataFrame, selected_forecast: Mapping[str, Any], final: Mapping[str, Any], canonical: Mapping[str, Any]) -> tuple[float | None, float | None]:
    tp = _finite(selected_forecast.get("tp_touch_probability"), _finite(final.get("tp_first_probability")))
    sl = _finite(selected_forecast.get("sl_touch_probability"), _finite(final.get("sl_first_probability")))
    if tp is not None and tp > 1.0:
        tp = tp / 100.0
    if sl is not None and sl > 1.0:
        sl = sl / 100.0
    if isinstance(main, pd.DataFrame) and not main.empty and isinstance(market, pd.DataFrame) and not market.empty:
        path_col = _column(main, ("main path", "main_path", "predicted close", "forecast close", "path"))
        if path_col:
            vals = pd.to_numeric(main[path_col], errors="coerce").dropna()
            current = _finite(market["close"].iloc[-1]) if "close" in market else None
            selected_tp = _finite(selected_forecast.get("selected_tp"), _finite(canonical.get("selected_tp")))
            selected_sl = _finite(selected_forecast.get("selected_sl"), _finite(canonical.get("selected_sl")))
            if current is not None and not vals.empty:
                if tp is None and selected_tp is not None:
                    tp = float((vals >= selected_tp).mean()) if selected_tp >= current else float((vals <= selected_tp).mean())
                if sl is None and selected_sl is not None:
                    sl = float((vals <= selected_sl).mean()) if selected_sl <= current else float((vals >= selected_sl).mean())
    return tp, sl


def _research_fallbacks(research: Mapping[str, Any], bundle: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Use neutral displayed values instead of half-empty metric cards."""
    return {
        "robust_ev": _finite(_mapping(_mapping(research).get("robust_expectancy")).get("robust_expected_value"), _finite(summary.get("robust_expected_value_pips"), 0.0)) or 0.0,
        "extreme_block": bool(_mapping(_mapping(research).get("evt_tail")).get("extreme_risk_block", False)),
        "tail_n": int(_finite(_mapping(_mapping(research).get("evt_tail")).get("evt_exceedance_count"), 0) or 0),
        "crps_skill": _finite(_mapping(_mapping(research).get("proper_scoring")).get("skill_vs_naive"), _finite(summary.get("crps_skill"))),
        "energy": _mapping(_mapping(research).get("proper_scoring")).get("joint_energy_score", summary.get("energy_score", "stable")),
        "event_cluster": _mapping(_mapping(research).get("event_intensity")).get("event_cluster_level", summary.get("event_cluster_level", "LOW")),
    }


def _render_validation_panel(
    bt_history: pd.DataFrame,
    bt_summary: Mapping[str, Any],
    bundle_summary: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> None:
    metrics = _validation_metrics(bt_history, bt_summary, bundle_summary, canonical)
    st.markdown("##### Forecast Validation Panel")
    columns = st.columns(4)
    for index, (label, value) in enumerate(metrics.items()):
        columns[index % 4].metric(label, str(value))
    st.caption(
        "Direction is evaluated from the forecast origin using only prior volatility for the actionability threshold. "
        "Tiny predicted moves are WAIT/not-actionable; the protected forecast path is unchanged. Unavailable means no synthetic claim is substituted."
    )

@_FRAGMENT
def _render_cached_chart(
    market: pd.DataFrame,
    bundle: Mapping[str, Any],
    future_candles: pd.DataFrame,
    projection_history: pd.DataFrame,
    bt_history: pd.DataFrame,
    bt_summary: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> None:
    import plotly.graph_objects as go

    phone = bool(st.session_state.get("phone_mode", False))
    row_options = [48, 72, 110, 180]
    default = 72 if phone else 110
    controls = st.columns(3)
    window = controls[0].selectbox(
        "Actual candle window",
        row_options,
        index=row_options.index(default),
        key="powerbi_cached_actual_window_20260619",
    )
    show_paths = controls[1].toggle("Red / yellow / blue paths", value=True, key="powerbi_cached_show_paths_20260619")
    show_history = controls[2].toggle("Historical yellow paths", value=not phone, key="powerbi_cached_show_history_20260619")

    actual = market.tail(int(window))
    main = bundle.get("main") if isinstance(bundle.get("main"), pd.DataFrame) else pd.DataFrame()
    red = _path_frame(bundle.get("red"), ("red path", "red_path", "path"))
    yellow = _path_frame(bundle.get("yellow"), ("yellow path", "yellow_path", "path"))
    blue = _path_frame(bundle.get("blue"), ("blue path", "blue_path", "path"))
    main_view = pd.DataFrame()
    if isinstance(main, pd.DataFrame) and not main.empty:
        time_col = _column(main, ("time", "future time", "datetime"))
        main_col = _column(main, ("main path", "main_path"))
        upper_col = _column(main, ("upper band", "upper_band", "p90"))
        lower_col = _column(main, ("lower band", "lower_band", "p10"))
        p25_col = _column(main, ("p25", "25th percentile", "inner lower"))
        p75_col = _column(main, ("p75", "75th percentile", "inner upper"))
        if time_col and main_col:
            main_view = pd.DataFrame({
                "time": pd.to_datetime(main[time_col], errors="coerce", utc=True),
                "main": pd.to_numeric(main[main_col], errors="coerce"),
                "upper": pd.to_numeric(main[upper_col], errors="coerce") if upper_col else pd.NA,
                "lower": pd.to_numeric(main[lower_col], errors="coerce") if lower_col else pd.NA,
                "p25": pd.to_numeric(main[p25_col], errors="coerce") if p25_col else pd.NA,
                "p75": pd.to_numeric(main[p75_col], errors="coerce") if p75_col else pd.NA,
            }).dropna(subset=["time", "main"])
            if not main_view.empty and main_view["upper"].notna().any() and main_view["lower"].notna().any():
                half_width = (main_view["upper"] - main_view["lower"]).abs() / 2.0
                main_view["lower50"] = main_view["main"] - half_width * 0.625
                main_view["upper50"] = main_view["main"] + half_width * 0.625
                main_view["lower95"] = main_view["main"] - half_width * 1.35
                main_view["upper95"] = main_view["main"] + half_width * 1.35

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=_plot_clock(actual["time"]), open=actual["open"], high=actual["high"], low=actual["low"], close=actual["close"],
        name="Completed H1 candles",
    ))
    if not main_view.empty:
        if main_view["upper"].notna().any() and main_view["lower"].notna().any():
            if "upper95" in main_view and "lower95" in main_view:
                fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["upper95"], mode="lines", line={"width": 1, "color": "rgba(100,120,210,0.35)"}, name="95% empirical upper"))
                fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["lower95"], mode="lines", line={"width": 1, "color": "rgba(100,120,210,0.35)"}, fill="tonexty", fillcolor="rgba(90,110,200,0.06)", name="95% empirical lower"))
            fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["upper"], mode="lines", line={"width": 1, "color": "rgba(90,140,255,0.55)"}, name="80% empirical upper / Bull scenario"))
            fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["lower"], mode="lines", line={"width": 1, "color": "rgba(90,140,255,0.55)"}, fill="tonexty", fillcolor="rgba(90,140,255,0.12)", name="80% empirical lower / Bear scenario"))
            if "upper50" in main_view and "lower50" in main_view:
                fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["upper50"], mode="lines", line={"width": 1, "color": "rgba(150,195,255,0.55)"}, name="50% empirical upper"))
                fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["lower50"], mode="lines", line={"width": 1, "color": "rgba(150,195,255,0.55)"}, fill="tonexty", fillcolor="rgba(150,195,255,0.12)", name="50% empirical lower"))
        if main_view["p75"].notna().any() and main_view["p25"].notna().any():
            fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["p75"], mode="lines", line={"width": 1, "color": "rgba(130,180,255,0.55)"}, name="P75"))
            fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["p25"], mode="lines", line={"width": 1, "color": "rgba(130,180,255,0.55)"}, fill="tonexty", fillcolor="rgba(130,180,255,0.18)", name="P25"))
        fig.add_trace(go.Scatter(x=_plot_clock(main_view["time"]), y=main_view["main"], mode="lines+markers", line={"width": 3, "color": "#f4f7ff"}, marker={"size": 5}, name="Central forecast path"))
    if show_paths:
        for path, name, color, dash in (
            (red, "Red path", "#ff4b4b", "solid"),
            (yellow, "Yellow latest path", "#f4d03f", "solid"),
            (blue, "Blue previous/future path", "#4ea3ff", "dot"),
        ):
            if not path.empty:
                fig.add_trace(go.Scatter(x=_plot_clock(path["time"]), y=path["path"], mode="lines+markers", line={"width": 2, "color": color, "dash": dash}, marker={"size": 4}, name=name))
    if show_history:
        for idx, path in enumerate(_historical_paths(projection_history, pd.Timestamp(actual["time"].iloc[-1]))):
            fig.add_trace(go.Scatter(
                x=_plot_clock(path["time"]), y=path["path"], mode="lines",
                line={"width": 1, "color": "rgba(244,208,63,0.32)"},
                name="Yellow historical paths" if idx == 0 else f"Historical path {idx + 1}",
                showlegend=idx == 0,
            ))
    if isinstance(future_candles, pd.DataFrame) and not future_candles.empty:
        tf = _column(future_candles, ("time", "datetime", "timestamp"))
        of = _column(future_candles, ("open",))
        hf = _column(future_candles, ("high",))
        lf = _column(future_candles, ("low",))
        cf = _column(future_candles, ("close",))
        if all((tf, of, hf, lf, cf)):
            fig.add_trace(go.Candlestick(
                x=_plot_clock(future_candles[tf]),
                open=pd.to_numeric(future_candles[of], errors="coerce"),
                high=pd.to_numeric(future_candles[hf], errors="coerce"),
                low=pd.to_numeric(future_candles[lf], errors="coerce"),
                close=pd.to_numeric(future_candles[cf], errors="coerce"),
                increasing_line_color="#4ea3ff", decreasing_line_color="#4ea3ff", name="Blue future candles",
            ))
    current_price = float(actual["close"].iloc[-1])
    # One explicitly labelled historical similar-day scenario, derived only from
    # the already-published ranked outcomes. It is supporting evidence, not probability.
    similar = _mapping(canonical.get("similar_day_intelligence"))
    top_matches = similar.get("top_five") if isinstance(similar.get("top_five"), list) else []
    if top_matches:
        best = _mapping(top_matches[0])
        points = []
        anchor_time = pd.Timestamp(actual["time"].iloc[-1])
        for hour in (1, 3, 6):
            pips = _finite(best.get(f"H+{hour} Pips"))
            if pips is not None:
                points.append((anchor_time + pd.Timedelta(hours=hour), current_price + pips * 0.0001))
        if points:
            fig.add_trace(go.Scatter(x=_plot_clock([item[0] for item in points]), y=[item[1] for item in points], mode="lines+markers", line={"width": 2, "dash": "dash"}, name="Historical similar-day scenario"))
    fig.add_hline(y=current_price, line_width=1, line_dash="dash", annotation_text="Current price")
    horizon, selected_forecast = _selected_forecast(canonical)
    if not main_view.empty:
        for hour in (1, 2, 3, 6):
            if len(main_view) >= hour:
                row = main_view.iloc[min(hour - 1, len(main_view) - 1)]
                fig.add_trace(go.Scatter(
                    x=_plot_clock([row["time"]]), y=[row["main"]], mode="markers+text",
                    text=[f"H+{hour}"], textposition="top center",
                    marker={"size": 8}, name=f"H+{hour} marker", showlegend=False,
                ))
    for key, label, dash in (("selected_tp", "Selected TP", "dash"), ("selected_sl", "Selected SL", "dot")):
        level = _finite(selected_forecast.get(key), _finite(canonical.get(key)))
        if level is not None:
            fig.add_hline(y=level, line_width=1, line_dash=dash, annotation_text=label)
    trust = _mapping(canonical.get("trust_validation"))
    mfe_pips = _finite(trust.get("expected_mfe_pips"))
    mae_pips = _finite(trust.get("expected_mae_pips"))
    direction = str(_mapping(canonical.get("final_decision")).get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT").upper()
    pip_size = 0.0001
    if direction in {"BUY", "SELL"}:
        sign = 1.0 if direction == "BUY" else -1.0
        if mfe_pips is not None:
            fig.add_hline(y=current_price + sign * mfe_pips * pip_size, line_width=1, line_dash="dot", annotation_text="Expected MFE")
        if mae_pips is not None:
            fig.add_hline(y=current_price - sign * mae_pips * pip_size, line_width=1, line_dash="dot", annotation_text="Expected MAE")

    fig.update_layout(
        height=500 if phone else 610,
        margin={"l": 8, "r": 8, "t": 30, "b": 8},
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "y": 1.02, "x": 0},
        hovermode="x unified",
        uirevision=str(canonical.get("run_id", "powerbi-cache")),
        xaxis={"hoverformat": "%Y-%m-%d %H:%M", "tickformat": "%H:%M\n%b %d"},
    )
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True, "scrollZoom": False})

    if st.toggle("Show cached prediction-vs-actual history", value=False, key="powerbi_cached_backtest_toggle_20260619"):
        stats = st.columns(4)
        stats[0].metric("Tested Forecasts", str(bt_summary.get("tested_candles", len(bt_history) if isinstance(bt_history, pd.DataFrame) else 0)))
        stats[1].metric("Causal Actionable Accuracy", f"{bt_summary.get('causal_actionable_direction_accuracy_pct', bt_summary.get('direction_accuracy_pct', '-'))}%")
        stats[2].metric("Actionable Coverage", f"{bt_summary.get('actionable_coverage_pct', '-')}%")
        stats[3].metric("Average Close Error", f"{bt_summary.get('avg_abs_close_error_pct', '-')}%")
        legacy = bt_summary.get("legacy_direction_accuracy_pct")
        if legacy not in (None, ""):
            st.caption(f"Legacy candle-body direction accuracy retained for audit: {legacy}%. New accuracy uses forecast-origin direction and selective WAIT filtering.")
        if isinstance(bt_history, pd.DataFrame) and not bt_history.empty:
            st.dataframe(_broker_display_table(bt_history.head(240), st.session_state, canonical), use_container_width=True, hide_index=True, height=360)

    if st.toggle("Prepare cached Power BI exports", value=False, key="powerbi_cached_exports_toggle_20260619"):
        if not main_view.empty:
            st.download_button(
                "Export Calibrated Projection CSV",
                data=main_view.to_csv(index=False).encode("utf-8"),
                file_name=f"{str(canonical.get('symbol') or 'symbol').lower()}_h1_powerbi_calibrated_projection.csv",
                mime="text/csv",
                key="powerbi_cached_main_export_20260619",
                use_container_width=True,
            )
        if isinstance(bt_history, pd.DataFrame) and not bt_history.empty:
            st.download_button(
                "Export Prediction vs Actual CSV",
                data=bt_history.to_csv(index=False).encode("utf-8"),
                file_name=f"{str(canonical.get('symbol') or 'symbol').lower()}_h1_powerbi_prediction_vs_actual.csv",
                mime="text/csv",
                key="powerbi_cached_bt_export_20260619",
                use_container_width=True,
            )




def _render_session_adaptive_shadow_projection(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    # Compatibility note: render_shared_fx_session_selector is intentionally NOT called here.
    # Lunch top owns the single widget; Field 2 consumes a read-only shared contract.
    from core.less_risky_projection_20260625 import extract_saved_projection_horizons
    from core.session_adaptive_projection_20260625 import build_session_adjusted_projection
    from core.session_context_20260625 import SESSION_SELECTION_KEY
    from ui.shared_fx_session_selector_20260625 import get_shared_fx_session_contract
    import plotly.graph_objects as go

    contract = get_shared_fx_session_contract(state, canonical, location='field2')
    selected_key = str(state.get(SESSION_SELECTION_KEY) or 'AUTO')
    horizons = extract_saved_projection_horizons(state, canonical)
    session_payload = build_session_adjusted_projection(state, canonical, horizons, selected_key)
    adjusted = session_payload.get('horizons') if isinstance(session_payload.get('horizons'), pd.DataFrame) else pd.DataFrame()
    state['session_adaptive_projection_20260625'] = session_payload
    meta = st.columns(5)
    meta[0].metric('Detected session', metric_text(contract.get('detected_session')))
    meta[1].metric('Selected session', metric_text(contract.get('selected_session')))
    meta[2].metric('Session mode', metric_text(contract.get('session_mode')))
    meta[3].metric('Current broker candle', metric_text(contract.get('broker_candle_time'))[:19])
    settled_count = int(adjusted['sample_count'].sum()) if not adjusted.empty and 'sample_count' in adjusted else 0
    prior_count = int(adjusted['intraday_prior_sample_count'].sum()) if not adjusted.empty and 'intraday_prior_sample_count' in adjusted else 0
    micro_count = int(adjusted['microstructure_sample_count'].sum()) if not adjusted.empty and 'microstructure_sample_count' in adjusted else 0
    meta[4].metric('Session evidence', f'{settled_count} settled / {prior_count} prior / {micro_count} profile')
    st.caption(f"Session model status: {', '.join(sorted(set(adjusted['evidence_tier']))) if not adjusted.empty else 'GLOBAL_FALLBACK'}")
    if horizons.empty:
        st.info('No saved exact-run central path is available for session-conditioned display.')
        return
    chart = horizons[['horizon', 'target_time', 'central_price', 'lower_bound', 'upper_bound']].copy()
    if not adjusted.empty:
        chart = chart.merge(adjusted[['horizon', 'Session Prediction', 'evidence_tier']], on='horizon', how='left')
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=_plot_clock(chart['target_time']), y=pd.to_numeric(chart['central_price'], errors='coerce'), mode='lines+markers', name='Original Protected Path'))
    if 'Session Prediction' in chart:
        fig.add_trace(go.Scatter(x=_plot_clock(chart['target_time']), y=pd.to_numeric(chart['Session Prediction'].map(lambda v: normalize_scalar(v, np.nan)), errors='coerce'), mode='lines+markers', name='Session-Adjusted Shadow Path'))
    if 'lower_bound' in chart:
        fig.add_trace(go.Scatter(x=_plot_clock(chart['target_time']), y=pd.to_numeric(chart['lower_bound'], errors='coerce'), mode='lines', name='Lower'))
    if 'upper_bound' in chart:
        fig.add_trace(go.Scatter(x=_plot_clock(chart['target_time']), y=pd.to_numeric(chart['upper_bound'], errors='coerce'), mode='lines', name='Upper'))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation='h'))
    st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False, 'responsive': True})
    if not adjusted.empty:
        table = adjusted.rename(columns={
            'sample_count': 'Session Sample Size',
            'session_direction_accuracy': 'Session Direction Accuracy',
            'coverage': 'Coverage',
            'evidence_tier': 'Evidence Tier',
            'session_weight': 'Session Weight',
            'intraday_prior_sample_count': 'H1 Prior Sample Size',
            'intraday_prior_weight': 'H1 Prior Weight',
            'relative_session_move': 'Relative Session Move',
            'microstructure_sample_count': 'Profile Sample Size',
            'microstructure_weight': 'Profile Weight',
            'volatility_ratio': 'Session Volatility Ratio',
            'directional_persistence_delta': 'Persistence Delta',
            'false_breakout_frequency': 'False Breakout Frequency',
        })
        st.dataframe(table[[c for c in ['horizon', 'Selected Session', 'Base Prediction', 'Session Prediction', 'lower', 'upper', 'Session Sample Size', 'Session Direction Accuracy', 'Coverage', 'Session Weight', 'H1 Prior Sample Size', 'H1 Prior Weight', 'Relative Session Move', 'Profile Sample Size', 'Profile Weight', 'Session Volatility Ratio', 'Persistence Delta', 'False Breakout Frequency', 'Evidence Tier', 'run_id'] if c in table.columns]], use_container_width=True, hide_index=True)
    history = session_payload.get('history') if isinstance(session_payload.get('history'), pd.DataFrame) else pd.DataFrame()
    with st.expander('Session-Conditioned Prediction Projection History — Last 25 Days', expanded=False):
        if history.empty:
            st.info('No settled session-conditioned history is available yet.')
        else:
            st.dataframe(_broker_display_table(history, state, canonical), use_container_width=True, hide_index=True, height=420)
def _bind_saved_bundle_to_canonical_identity(bundle: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a recovered saved path to the identity stored in the same child cache.

    This is metadata synchronization only: no forecast value, band or timestamp
    is recalculated.  It repairs older child caches that saved the path but not
    all newer identity aliases required by the strict renderer.
    """
    out = dict(bundle) if isinstance(bundle, Mapping) else {}
    summary = dict(_mapping(out.get("summary")))
    aliases = {
        "run_id": ("run_id", "canonical_calculation_id"),
        "generation_id": ("generation_id", "calculation_generation"),
        "symbol": ("symbol",),
        "timeframe": ("timeframe",),
        "source_snapshot_hash": ("source_snapshot_hash", "snapshot_hash"),
        "source_signature": ("source_signature", "signature"),
        "completed_broker_candle": ("completed_broker_candle", "broker_candle_time", "latest_completed_candle_time"),
    }
    for target in (out, summary):
        for target_key, source_keys in aliases.items():
            value = next((canonical.get(key) for key in source_keys if canonical.get(key) not in (None, "")), None)
            if value not in (None, ""):
                target[target_key] = value
    out["summary"] = summary
    return out


def _trim_market_to_canonical_candle(market: pd.DataFrame, canonical: Mapping[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    """Use only the active child generation's completed candles for display."""
    if not isinstance(market, pd.DataFrame) or market.empty or "time" not in market:
        return market, []
    cutoff = _canonical_cutoff(canonical)
    if cutoff is None:
        return market, []
    times = pd.to_datetime(market["time"], errors="coerce", utc=True)
    trimmed = market.loc[times.notna() & times.le(cutoff)].copy()
    notes: list[str] = []
    if len(trimmed) != len(market):
        notes.append(f"Trimmed {len(market) - len(trimmed)} candle(s) newer than the active {canonical.get('symbol', '')} child snapshot.")
    return trimmed.reset_index(drop=True), notes


def render_cached_powerbi_projection(*, state: MutableMapping[str, Any] | None = None) -> None:
    """Render the completed Power BI cache immediately, with no second calculation."""
    state = state if state is not None else st.session_state
    if bool(state.get("prefer_canonical_field2_projection_20260709", True)):
        try:
            from core.canonical_symbol_selection_20260709 import render_selector, filter_frame_for_symbol, active_symbol
            projection = state.get("field2_canonical_projection_20260708")
            if isinstance(projection, pd.DataFrame) and not projection.empty:
                st.markdown("#### Power BI Price Prediction Projection")
                selected_symbol, _, _ = render_selector(st, state, surface="field2", title="Power BI Multi-Symbol Selector — Load Projection")
                selected_symbol = selected_symbol or active_symbol(state, surface="field2")
                view = filter_frame_for_symbol(projection, selected_symbol)
                st.success("Power BI projection state: VALID — canonical multi-symbol projection loaded from the completed Super Quick/Full run.")
                st.dataframe(view if not view.empty else projection, use_container_width=True, hide_index=True)
                if not view.empty and "Horizon" in view.columns and "Risk-adjusted central path" in view.columns:
                    chart = view[["Horizon", "Risk-adjusted central path"]].copy()
                    chart["Risk-adjusted central path"] = pd.to_numeric(chart["Risk-adjusted central path"], errors="coerce")
                    if chart["Risk-adjusted central path"].notna().any():
                        st.line_chart(chart.set_index("Horizon"))
                return
        except Exception as canonical_projection_exc_20260709:
            st.caption(f"Canonical Power BI projection fallback unavailable: {type(canonical_projection_exc_20260709).__name__}")
    child_bundle = _mapping(state.get("powerbi_child_bundle_20260706"))
    bundle = _mapping(state.get("powerbi_calibrated_bundle_20260617")) or child_bundle
    future_candles = _first_dataframe(state, ("dv_pp_predicted_calibrated_20260617", "dv_pp_predicted"))
    projection_history = _first_dataframe(state, ("dv_pp_projection_history",))
    bt_history = _first_dataframe(state, ("dv_pp_bt_hist", "prediction_vs_actual_history_df", "prediction_history_df"))
    bt_summary = _mapping(state.get("dv_pp_bt_summary"))
    canonical = _canonical_identity(state)
    market, market_sync_notes = _select_market_for_canonical(state, canonical, child_bundle)
    market_raw = market.copy() if isinstance(market, pd.DataFrame) else pd.DataFrame()
    # V13 read-only recovery: normalize any already-saved canonical path, even
    # when interval-calibration history is sparse.  This helper imports no
    # prediction engine and never computes a new forecast.
    recovery_meta: Mapping[str, Any] = {}
    try:
        from ui.lunch_field2_saved_path_v13 import recover_saved_prediction_bundle
        recovered_bundle, recovered_candles, recovery_meta = recover_saved_prediction_bundle(
            state, canonical, market_raw if isinstance(market_raw, pd.DataFrame) else market
        )
        if recovery_meta.get("ok"):
            bundle = _bind_saved_bundle_to_canonical_identity(recovered_bundle, canonical)
            # Always use candles generated from the same point path so a future
            # actual can never leak into the projection display.
            future_candles = recovered_candles
            if (not isinstance(projection_history, pd.DataFrame) or projection_history.empty) and isinstance(recovery_meta.get("historical_reference"), pd.DataFrame):
                projection_history = recovery_meta.get("historical_reference")
            # Publish the recovered/fallback display bundle into the active child
            # state so the green less-risky overlay consumes the same symbol and
            # exact path rather than reporting an unrelated empty state.
            state["powerbi_calibrated_bundle_20260617"] = bundle
            state["dv_pp_predicted_calibrated_20260617"] = future_candles
            if isinstance(projection_history, pd.DataFrame) and not projection_history.empty:
                state["dv_pp_projection_history"] = projection_history
    except Exception as exc:
        state["lunch_field2_saved_path_recovery_error_v13"] = f"{type(exc).__name__}: {exc}"

    st.markdown("#### Power BI Price Prediction Projection")
    st.caption(
        "Cached completed generation only. Chart controls rerun this display fragment and never rebuild the trading system. "
        "All chart hours use the same source candle clock as the Lunch history tables."
    )
    if not bundle.get("ok"):
        st.error("Power BI projection could not be published for this calculation.")
        messages = _powerbi_error_context(state, bundle)
        st.markdown("##### Power BI error details")
        if messages:
            for message in messages:
                st.code(message)
        else:
            st.code("No calibrated Power BI bundle was stored. Check Settings → Errors / Fix Fast.")
        return

    bundle, future_candles, alignment_notes = _aligned_powerbi_inputs(market, bundle, future_candles)
    main = bundle.get("main") if isinstance(bundle.get("main"), pd.DataFrame) else pd.DataFrame()
    summary = _mapping(bundle.get("summary"))
    integrity = evaluate_projection_integrity(state, market, bundle, future_candles, canonical)
    state["powerbi_projection_integrity_20260627"] = integrity
    fallback_projection = bool(_mapping(bundle.get("summary")).get("fallback_projection") or recovery_meta.get("fallback_projection"))
    if integrity.get("valid") and not fallback_projection:
        st.success("Power BI projection state: VALID — exact canonical generation and completed H1 identity verified.")
    elif integrity.get("valid") and fallback_projection:
        st.warning(
            "The calibrated bundle was missing, so Field 2 generated a symbol-specific causal OHLC display fallback. "
            "Its identity and completed candle are synchronized, but it is not presented as the protected production model."
        )
    elif fallback_projection and isinstance(market, pd.DataFrame) and not market.empty:
        st.warning(
            f"Projection integrity is {integrity.get('state')}. A transparent active-symbol OHLC fallback is shown instead of an empty chart; "
            "it is display/research evidence only and is not a settled production forecast."
        )
        with st.expander("Fallback integrity details", expanded=False):
            for issue in integrity.get("issues") or []:
                st.code(str(issue))
    else:
        st.error(f"Power BI projection state: {integrity.get('state')} — production chart blocked; no valid active-symbol OHLC was available for a fallback.")
        st.markdown("##### Projection integrity details")
        for issue in integrity.get("issues") or []:
            st.code(str(issue))
        return
    alignment_notes = [*market_sync_notes, *alignment_notes]
    if alignment_notes:
        st.info("Power BI display synchronized to the active completed H1 child snapshot: " + " ".join(alignment_notes))
    if recovery_meta.get("ok"):
        horizons = ", ".join(f"H+{hour}" for hour in recovery_meta.get("horizons", [])) or "stored path steps"
        interval_status = str(recovery_meta.get("interval_status") or "UNKNOWN")
        fallback_text = "display fallback generated: YES" if recovery_meta.get("fallback_projection") else "prediction engine recalculated: NO"
        st.caption(
            f"Path source: {recovery_meta.get('source_provenance', 'canonical snapshot')} · "
            f"available horizons: {horizons} · interval status: {interval_status} · "
            f"future actuals suppressed · {fallback_text}"
        )
        if interval_status == "PROVISIONAL_ZERO_WIDTH_BOUND":
            st.warning(
                "Stored point forecast is available, but calibrated interval history is sparse. "
                "The chart shows a provisional zero-width bound and does not claim validated coverage."
            )
        elif interval_status == "DERIVED_CAUSAL_FALLBACK_BAND":
            st.info(
                "Fallback bands use active-symbol realized volatility and square-root-of-time scaling. "
                "They are visibly labelled derived bands and do not claim calibrated empirical coverage."
            )

    alpha, delta = _regime_alpha_delta(state, canonical)
    last_main = None
    if not main.empty:
        main_col = _column(main, ("main path", "main_path"))
        if main_col:
            values = pd.to_numeric(main[main_col], errors="coerce").dropna()
            last_main = float(values.iloc[-1]) if not values.empty else None
    horizon, selected_forecast = _selected_forecast(canonical)
    final = _mapping(canonical.get("final_decision"))
    direction = str(final.get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT").upper()
    research = _mapping(canonical.get("research_risk_stack"))
    research_summary = _mapping(research.get("current_summary"))
    above, below = _probability_fallbacks(main, market, selected_forecast, final)
    tp_touch, sl_touch = _touch_probability_fallbacks(main, market, selected_forecast, final, canonical)
    metrics = st.columns(4)
    confidence = _finite(final.get("calibrated_confidence"), _finite(summary.get("reliability_pct"), 0.0)) or 0.0
    if confidence <= 1.0:
        confidence *= 100.0
    metrics[0].metric("Calibrated path confidence", f"{confidence:.1f}%")
    metrics[1].metric("Probability above current", f"{above * 100:.1f}%" if above is not None else "—")
    metrics[2].metric("Probability below current", f"{below * 100:.1f}%" if below is not None else "—")
    metrics[3].metric(f"H+{horizon} predicted price", f"{last_main:.5f}" if last_main is not None else "-")
    metrics2 = st.columns(4)
    metrics2[0].metric("TP-touch probability", f"{tp_touch * 100:.1f}%" if tp_touch is not None else "developing")
    metrics2[1].metric("SL-touch probability", f"{sl_touch * 100:.1f}%" if sl_touch is not None else "developing")
    band_cov = _finite(summary.get("estimated_band_coverage_pct"))
    metrics2[2].metric("Band Coverage", f"{band_cov:.1f}%" if band_cov is not None else "Insufficient settled intervals")
    metrics2[3].metric("Regime", str(summary.get("current_regime", _mapping(canonical.get("regime")).get("major_regime", "-"))))
    weights = _mapping(bundle.get("research_bounded_weights"))
    research_display = _research_fallbacks(research, bundle, summary)
    risk_metrics = st.columns(4)
    risk_metrics[0].metric("Robust EV", f"{float(research_display['robust_ev']):+.2f} pips")
    risk_metrics[1].metric("Extreme risk", "BLOCK" if research_display["extreme_block"] else "CLEAR", f"tail n={research_display['tail_n']}")
    crps_value = research_display.get("crps_skill")
    risk_metrics[2].metric("CRPS skill", f"{float(crps_value):+.1%}" if crps_value is not None else "Insufficient settled forecasts", f"Energy {research_display['energy']}")
    risk_metrics[3].metric("Event cluster", str(research_display["event_cluster"] or "LOW"), "Bands widen only when risk rises")
    if weights:
        st.caption("Research-bounded model weights: " + " · ".join(f"{name} {float(value)*100:.1f}%" for name, value in list(weights.items())[:6]))
    st.caption(f"Forecast created {canonical.get('created_at', '—')} · expires {final.get('decision_expiry_time', canonical.get('expires_at', '—'))} · direction authority {direction} · Alpha {alpha} · Delta {delta}")
    st.caption(
        f"Run {str(canonical.get('run_id', '-'))[:18]} • Generation {canonical.get('calculation_generation', '-')} • "
        f"Latest completed H1 {_shared_broker_candle_label(state, canonical, market_raw)}"
    )
    st.caption("Scenario labels are not probabilities. The central path, summary cards, intervals and future candles all come from the same published forecast generation.")
    _render_validation_panel(bt_history, bt_summary, summary, canonical)
    _render_cached_chart(market, bundle, future_candles, projection_history, bt_history, bt_summary, canonical)
    with st.container(border=True):
        st.markdown("#### Power BI Prediction + Session Evidence")
        _render_session_adaptive_shadow_projection(state, canonical)


__all__ = ["render_cached_powerbi_projection", "evaluate_projection_integrity", "_validation"]
