"""Fast compute-only Field 3 path for the Super Quick button.

This runner intentionally calculates only the compact Field 3 tables requested by the user:
1) Regime Age Ranking — Candle After Regime Start Only
2) Middle Regime Age Ranking — Candle After Middle Regime Start Only
3) Higher Standard Summary

The heavier protected, AI, research, Field 10/11, trust-history and validation
pipelines remain owned by Quick/Full. No provider call is made here; the runner
uses only frames already validated by the Settings Load controls.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import json
import math
import time
import uuid

import numpy as np
import pandas as pd

from core.calculation.run_orchestrator import MARKET_RESULTS_KEY
from core.field3_three_regime_engine import standard_windows, standardize_candles
from core.global_symbol_context import get_global_symbol_context, publish_completed_generation
from core.regime_duration_stats_20260729 import completed_regime_run_stats

FAST_RUN_VERSION = "field3-three-table-fast-v4-20260729"


def _clip(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        return float(np.clip(float(value), low, high))
    except Exception:
        return low


def _sigmoid(value: float) -> float:
    value = float(np.clip(value, -20.0, 20.0))
    return float(1.0 / (1.0 + math.exp(-value)))


def _trailing_run_length(values: pd.Series) -> int:
    if values.empty:
        return 0
    current = values.iloc[-1]
    count = 0
    for value in values.iloc[::-1]:
        if value != current:
            break
        count += 1
    return int(count)


def _fast_standard(frame: pd.DataFrame, *, standard: str, window_bars: int) -> dict[str, Any]:
    """Vectorized deterministic regime estimate suitable for the fast lane.

    Quick/Full continue to own the Hamilton/BOCPD research implementation. The
    fast lane uses completed-candle trend, normalized EMA separation, slope and
    volatility so a 30-symbol loaded universe can be processed in seconds rather
    than entering the heavy Quick/Full research pipeline.
    """
    df = standardize_candles(frame)
    if df.empty or len(df) < 25:
        return {
            "standard": standard,
            "state": "UNAVAILABLE",
            "bias": "BLOCKED",
            "probability": 0.0,
            "persistence": 0.0,
            "expected_duration": 0.0,
            "age": 0,
            "transition_risk": 1.0,
            "reliability": 0.0,
            "sample_count": int(len(df)),
            "quality_grade": "F",
            "completed_candle": "",
            "status": "BLOCKED",
        }

    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    if len(close) < 25:
        return {
            "standard": standard, "state": "UNAVAILABLE", "bias": "BLOCKED",
            "probability": 0.0, "persistence": 0.0, "expected_duration": 0.0,
            "age": 0, "transition_risk": 1.0, "reliability": 0.0,
            "sample_count": int(len(close)), "quality_grade": "F",
            "completed_candle": str(df["open_time"].iloc[-1].isoformat()), "status": "BLOCKED",
        }

    window = max(8, min(int(window_bars), len(close) - 1))
    fast_span = max(3, window // 5)
    slow_span = max(fast_span + 2, window // 2)
    ema_fast = close.ewm(span=fast_span, adjust=False).mean()
    ema_slow = close.ewm(span=slow_span, adjust=False).mean()

    prev_close = close.shift(1)
    true_range = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = true_range.ewm(span=max(5, window // 3), adjust=False).mean().replace(0, np.nan)
    normalized_gap = ((ema_fast - ema_slow) / atr).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    slope_window = max(5, min(window // 3, 40))
    slope = close.pct_change(slope_window).fillna(0.0)
    vol = close.pct_change().rolling(max(8, min(window, 60)), min_periods=5).std().replace(0, np.nan)
    normalized_slope = (slope / (vol * math.sqrt(max(1, slope_window)))).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    score = 0.72 * normalized_gap + 0.28 * normalized_slope

    # A modest neutral band prevents tiny noise from repeatedly resetting age.
    threshold = 0.18
    states = pd.Series(
        np.where(score > threshold, "BULL", np.where(score < -threshold, "BEAR", "NEUTRAL")),
        index=close.index,
    )
    current_state = str(states.iloc[-1])
    age = _trailing_run_length(states)
    completed_run_stats = completed_regime_run_stats(states.tolist(), current_value=current_state)
    bias = "BUY" if current_state == "BULL" else "SELL" if current_state == "BEAR" else "NEUTRAL"
    strength = abs(float(score.iloc[-1]))
    probability = _clip(0.50 + 0.49 * (2.0 * _sigmoid(strength * 1.7) - 1.0), 0.50, 0.99)
    persistence = _clip(age / max(3.0, min(float(window), 30.0)), 0.0, 0.98)
    expected_duration = float(max(age, round(1.0 / max(0.02, 1.0 - persistence), 2)))
    transition_risk = _clip((1.0 - persistence) * 0.65 + (0.35 if current_state == "NEUTRAL" else 0.0))
    completeness = _clip(len(close) / max(45.0, float(window_bars)))
    reliability = _clip(0.40 * probability + 0.35 * persistence + 0.25 * completeness)
    quality_grade = "A" if completeness >= 0.95 else "B" if completeness >= 0.75 else "C" if completeness >= 0.50 else "D"

    return {
        "standard": standard,
        "state": current_state,
        "bias": bias,
        "probability": probability,
        "persistence": persistence,
        "expected_duration": expected_duration,
        "age": age,
        "avg_regime_candle_count_before_change": completed_run_stats.get("average"),
        "completed_regime_run_count": int(completed_run_stats.get("count") or 0),
        "avg_regime_duration_basis": completed_run_stats.get("basis"),
        "transition_risk": transition_risk,
        "reliability": reliability,
        "sample_count": int(len(close)),
        "quality_grade": quality_grade,
        "completed_candle": str(df["open_time"].iloc[-1].isoformat()),
        "status": "READY",
        "score": float(score.iloc[-1]),
        "window_bars": int(window_bars),
    }


def _extract_loaded_frames(state: Mapping[str, Any], requested_symbols: list[str]) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    report = state.get(MARKET_RESULTS_KEY)
    report = report if isinstance(report, Mapping) else {}
    raw_results = report.get("results") if isinstance(report.get("results"), Mapping) else {}
    frames: dict[str, pd.DataFrame] = {}
    failures: dict[str, str] = {}
    for symbol in requested_symbols:
        payload = raw_results.get(symbol) if isinstance(raw_results.get(symbol), Mapping) else {}
        frame = standardize_candles(payload.get("frame"))
        if frame.empty:
            failures[symbol] = "MISSING_VALIDATED_PRELOADED_FRAME"
        else:
            frames[symbol] = frame
    return frames, failures


def _fast_input_signature(
    frames: Mapping[str, pd.DataFrame], *, selected: list[str], timeframe: str,
    failures: Mapping[str, str] | None = None,
) -> str:
    """Hash the exact bounded candles used by the fast calculation.

    A repeated Super Quick click with unchanged loaded candles can reuse the
    already-published tables instead of recalculating or writing SQLite again.
    """
    digest = sha256()
    digest.update(FAST_RUN_VERSION.encode("utf-8"))
    digest.update(str(timeframe).encode("utf-8"))
    digest.update("|".join(selected).encode("utf-8"))
    for symbol in selected:
        digest.update(symbol.encode("utf-8"))
        frame = frames.get(symbol)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            digest.update(str((failures or {}).get(symbol, "MISSING")).encode("utf-8"))
            continue
        columns = [column for column in ("open_time", "open", "high", "low", "close", "volume") if column in frame.columns]
        bounded = frame.loc[:, columns].tail(800)
        digest.update(str(len(frame)).encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(bounded, index=False).values.tobytes())
    return digest.hexdigest()


def _build_rows(
    frames: Mapping[str, pd.DataFrame], *, timeframe: str, run_id: str, generation: int,
    snapshot_hash: str, progress_callback: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    windows = standard_windows(timeframe)
    ranking_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    failures: dict[str, str] = {}
    symbols = list(frames)
    total = max(1, len(symbols))

    for index, symbol in enumerate(symbols, start=1):
        try:
            frame = frames[symbol]
            # Lower is deliberately calculated in the fast lane now. This is a
            # bounded EMA/ATR/slope calculation, not the heavy Quick/Full
            # research pipeline, so three-bias agreement can be displayed
            # truthfully without materially slowing Super Quick.
            lower = _fast_standard(frame, standard="LOWER", window_bars=windows["LOWER"])
            middle = _fast_standard(frame, standard="MIDDLE", window_bars=windows["MIDDLE"])
            higher = _fast_standard(frame, standard="HIGHER", window_bars=windows["HIGHER"])
            for item in (lower, middle, higher):
                payload = {
                    "status": item["status"],
                    "model": "FAST_EMA_ATR_SLOPE_REGIME",
                    "fast_lane_version": FAST_RUN_VERSION,
                    "score": item.get("score"),
                    "window_bars": item.get("window_bars"),
                    "avg_regime_candle_count_before_change": item.get("avg_regime_candle_count_before_change"),
                    "completed_regime_run_count": item.get("completed_regime_run_count"),
                    "avg_regime_duration_basis": item.get("avg_regime_duration_basis"),
                }
                evidence_hash = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
                evidence_rows.append({
                    "Parent Run ID": run_id,
                    "Generation": int(generation),
                    "Symbol": symbol,
                    "Timeframe": timeframe,
                    "Standard": item["standard"],
                    "Window Bars": int(item.get("window_bars") or windows[item["standard"]]),
                    "Regime State": item["state"],
                    "Bias": item["bias"],
                    "Posterior Probability": float(item["probability"]),
                    "Persistence Probability": float(item["persistence"]),
                    "Expected Duration": float(item["expected_duration"]),
                    "Regime Age": int(item["age"]),
                    "Changepoint Probability": float(item["transition_risk"]),
                    "Transition Risk": float(item["transition_risk"]),
                    "Calibrated Reliability": float(item["reliability"]),
                    "Signed Evidence Score": float(item.get("score") or 0.0),
                    "Sample Count": int(item["sample_count"]),
                    "Data Quality Grade": item["quality_grade"],
                    "Completed Candle": item["completed_candle"],
                    "Evidence Hash": evidence_hash,
                    "Payload JSON": json.dumps(payload, default=str),
                })

            higher_state = higher["state"]
            higher_bias = higher["bias"]
            middle_state = middle["state"]
            middle_bias = middle["bias"]
            lower_state = lower["state"]
            lower_bias = lower["bias"]
            composite_bias = higher_bias if higher_bias in {"BUY", "SELL"} else middle_bias
            decision_strength = float(
                0.60 * higher["reliability"]
                + 0.25 * middle["reliability"]
                + 0.15 * lower["reliability"]
            )
            rank_payload = {
                "fast_lane_version": FAST_RUN_VERSION,
                "higher": higher,
                "middle": middle,
                "lower": lower,
            }
            rank_hash = sha256(json.dumps(rank_payload, sort_keys=True, default=str).encode()).hexdigest()
            ranking_rows.append({
                "Rank": None,
                "Symbol": symbol,
                "Lower Regime": lower_state, "Lower Bias": lower_bias,
                "Lower Probability": lower["probability"], "Lower Reliability": lower["reliability"],
                "Middle Regime": middle_state, "Middle Bias": middle_bias,
                "Middle Probability": middle["probability"], "Middle Reliability": middle["reliability"],
                "Higher Regime": higher_state, "Higher Bias": higher_bias,
                "Higher Probability": higher["probability"], "Higher Reliability": higher["reliability"],
                "Three-Regime Agreement": (
                    1.0 if lower_bias == middle_bias == higher_bias
                    else 2.0 / 3.0 if len({lower_bias, middle_bias, higher_bias}) == 2
                    else 0.0
                ),
                "Directional Conflict": "YES" if {"BUY", "SELL"}.issubset({lower_bias, middle_bias, higher_bias}) else "NO",
                "Dominant Standard": "HIGHER",
                "Changepoint Risk": higher["transition_risk"],
                "Transition Risk": higher["transition_risk"],
                "DCC Correlation Penalty": 0.0,
                "HRP Cluster": 0,
                "Spillover TO": 0.0, "Spillover FROM": 0.0, "Net Spillover": 0.0,
                "Composite Bias": composite_bias,
                "Composite Score": float(higher.get("score") or 0.0),
                "Decision Strength": decision_strength,
                "Calibrated Reliability": float(higher["reliability"]),
                "Entry Permission": "FAST_SUMMARY_ONLY",
                "Lower Candle After Regime Start": int(lower["age"]),
                "Middle Candle After Regime Start": int(middle["age"]),
                "Middle Avg Regime Candle Count Before Regime Change": middle.get("avg_regime_candle_count_before_change"),
                "Middle Completed Regime Sample Count": int(middle.get("completed_regime_run_count") or 0),
                "Higher Candle After Regime Start": int(higher["age"]),
                "Candle After Regime Start": int(higher["age"]),
                "Regime Start Standard": "HIGHER",
                "Block Reason": "HEAVY_VALIDATION_DEFERRED_TO_QUICK",
                "Completed Candle": higher["completed_candle"],
                "Parent Run ID": run_id,
                "Generation": int(generation),
                "Timeframe": timeframe,
                "Snapshot Hash": snapshot_hash,
                "Evidence Hash": rank_hash,
                "Source Data Hash": "",
                "Rank Explanation": json.dumps(rank_payload, default=str),
                "Walk-Forward Decision Threshold": "DEFERRED_TO_QUICK",
                "Adaptive Decision Threshold": "DEFERRED_TO_QUICK",
            })
        except Exception as exc:
            failures[symbol] = f"{type(exc).__name__}: {exc}"

        if callable(progress_callback):
            percent = 8.0 + 82.0 * (index / total)
            completed_set = {row["Symbol"] for row in ranking_rows}
            progress_callback({
                "overall_percent": percent,
                "current_symbol": symbol,
                "current_stage": "Building fast Lower/Middle/Higher regime state and recent-age ranks",
                "completed_symbols": index,
                "total_symbols": total,
                "symbols": {
                    s: {
                        "status": "COMPLETED" if s in completed_set else "FAILED" if s in failures else "WAITING",
                        "percent": 100 if s in completed_set else 0,
                        "stage": "Fast three-table Field 3",
                        "calculation_scope": "LUNCH_CORE",
                    }
                    for s in symbols
                },
            })

    ranking = pd.DataFrame(ranking_rows)
    if not ranking.empty:
        ranking["Rank"] = pd.to_numeric(ranking["Candle After Regime Start"], errors="coerce").rank(
            method="min", ascending=True, na_option="bottom"
        ).astype("Int64")
        ranking = ranking.sort_values(["Rank", "Symbol"], kind="mergesort").reset_index(drop=True)
    return ranking, pd.DataFrame(evidence_rows), failures


def run_super_quick_field3(
    state: MutableMapping[str, Any], *, symbols: list[str] | None = None,
    timeframe: str | None = None, progress_callback: Any = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    context = get_global_symbol_context(state)
    selected = [str(s).strip().upper() for s in (symbols or list(context.loaded_symbols)) if str(s).strip()]
    tf = str(timeframe or context.timeframe or state.get("timeframe") or "H1").strip().upper() or "H1"
    if not selected:
        raise RuntimeError("NO_LOADED_SYMBOLS_FOR_SUPER_QUICK")

    if callable(progress_callback):
        progress_callback({"overall_percent": 3.0, "current_symbol": selected[0], "current_stage": "Reading validated loaded candles"})

    frames, failures = _extract_loaded_frames(state, selected)
    if not frames:
        raise RuntimeError("NO_VALIDATED_PRELOADED_FRAMES_FOR_SUPER_QUICK")

    # Align every symbol to the latest candle shared by all loaded frames. This
    # prevents a mixed-cutoff publication failure without fetching any data.
    common_cutoff = min(frame["open_time"].iloc[-1] for frame in frames.values())
    aligned_frames = {
        symbol: frame.loc[frame["open_time"] <= common_cutoff].copy().reset_index(drop=True)
        for symbol, frame in frames.items()
    }
    aligned_frames = {symbol: frame for symbol, frame in aligned_frames.items() if not frame.empty}
    input_signature = _fast_input_signature(
        aligned_frames, selected=selected, timeframe=tf, failures=failures,
    )
    cached_result = state.get("super_quick_field3_cached_result_20260727")
    cached_ranking = state.get("field3_multisymbol_regime_20260708")
    cached_evidence = state.get("field3_regime_evidence_v2")
    if (
        str(state.get("super_quick_field3_input_signature_20260727") or "") == input_signature
        and isinstance(cached_result, Mapping)
        and isinstance(cached_ranking, pd.DataFrame) and not cached_ranking.empty
        and "Symbol" in cached_ranking.columns
        and isinstance(cached_evidence, pd.DataFrame) and not cached_evidence.empty
        and set(cached_ranking["Symbol"].astype(str)) == set(aligned_frames)
    ):
        elapsed = round(time.perf_counter() - started, 3)
        reused = {
            **dict(cached_result),
            "status": "COMPLETED" if not failures else "PARTIAL",
            "ok": True,
            "selected_symbols": list(selected),
            "elapsed_seconds": elapsed,
            "provider_requests": 0,
            "reused_cached_calculation": True,
            "cache_signature": input_signature,
        }
        state["field3_fast_two_table_mode_20260722"] = True
        state["field3_fast_three_table_mode_20260729"] = True
        state["field3_last_run_scope_20260722"] = "LUNCH_CORE"
        state["settings_run_status_20260617"] = reused
        if callable(progress_callback):
            progress_callback({
                "overall_percent": 100.0,
                "current_symbol": selected[-1],
                "current_stage": "Unchanged candles — reused cached all-loaded Field 3 result",
                "completed_symbols": len(aligned_frames),
                "total_symbols": len(selected),
            })
        return reused

    run_id = f"SQF3-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    generation = int(context.generation or 1)
    snapshot_hash = sha256(
        json.dumps({"run_id": run_id, "symbols": list(aligned_frames), "timeframe": tf, "cutoff": common_cutoff.isoformat()}, sort_keys=True).encode()
    ).hexdigest()

    ranking, evidence, calculation_failures = _build_rows(
        aligned_frames, timeframe=tf, run_id=run_id, generation=generation,
        snapshot_hash=snapshot_hash, progress_callback=progress_callback,
    )
    failures.update(calculation_failures)
    completed_symbols = ranking["Symbol"].astype(str).tolist() if not ranking.empty else []
    if not completed_symbols:
        raise RuntimeError("SUPER_QUICK_NO_SYMBOL_COMPLETED")

    state["field3_multisymbol_regime_20260708"] = ranking
    state["field3_regime_evidence_v2"] = evidence
    state["field3_research_validation_v2"] = pd.DataFrame()
    state["field3_fast_two_table_mode_20260722"] = True
    state["field3_fast_three_table_mode_20260729"] = True
    state["field3_last_run_scope_20260722"] = "LUNCH_CORE"
    state["super_quick_field3_run_20260722"] = {
        "run_id": run_id,
        "symbols": completed_symbols,
        "failed": dict(failures),
        "timeframe": tf,
        "common_completed_candle": common_cutoff.isoformat(),
        "version": FAST_RUN_VERSION,
    }

    # Persist the compact evidence for reloads. Persistence is non-blocking; the
    # session result remains usable even if the local database is unavailable.
    persistence_status: dict[str, Any]
    try:
        from core.field3_three_regime_engine import persist_field3_v2
        persistence_status = {"ok": True, **persist_field3_v2(ranking, evidence)}
    except Exception as exc:
        persistence_status = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        state["super_quick_field3_persistence_warning_20260722"] = persistence_status["error"]

    publication_status: dict[str, Any]
    try:
        completion_members = {
            symbol: {
                "timeframe": tf,
                "latest_completed_candle": common_cutoff.isoformat(),
                "data_quality_grade": "FAST_VALIDATED",
            }
            for symbol in completed_symbols
        }
        published = publish_completed_generation(
            context.universe_id,
            completion_members,
            parent_run_id=run_id,
            snapshot_hash=snapshot_hash,
            latest_completed_candle=common_cutoff.isoformat(),
            calculation_depth="SUPER_QUICK_FIELD3_THREE_TABLES",
            state=state,
        )
        publication_status = {"ok": True, "status": published.publication_status, "generation": published.generation}
    except Exception as exc:
        # Unlike the legacy global contract, a publication warning never discards
        # valid symbol rows. The exact completed rows stay visible in Field 3.
        publication_status = {"ok": False, "status": "SESSION_RESULT_PUBLISHED", "error": f"{type(exc).__name__}: {exc}"}
        state["super_quick_field3_publication_warning_20260722"] = publication_status["error"]

    elapsed = round(time.perf_counter() - started, 3)
    if callable(progress_callback):
        progress_callback({
            "overall_percent": 100.0,
            "current_symbol": completed_symbols[-1],
            "current_stage": "Fast Field 3 three-table result ready",
            "completed_symbols": len(completed_symbols),
            "total_symbols": len(selected),
        })

    status = "COMPLETED" if not failures else "PARTIAL"
    result = {
        "status": status,
        "ok": bool(completed_symbols),
        "run_id": run_id,
        "parent_run_id": run_id,
        "calculation_generation": generation,
        "calculation_scope": "SUPER_QUICK_FIELD3_THREE_TABLES",
        "selected_symbols": selected,
        "completed_symbol_list": completed_symbols,
        "completed_symbols": len(completed_symbols),
        "failed_symbol_list": sorted(failures),
        "failed_symbols": len(failures),
        "symbol_status": {
            symbol: {"status": "COMPLETED" if symbol in completed_symbols else "FAILED", "error": failures.get(symbol, "")}
            for symbol in selected
        },
        "completion_contract": {
            "ok": bool(completed_symbols),
            "status": "FAST_THREE_TABLE_READY" if completed_symbols else "FAILED",
            "selected_count": len(selected),
            "field3_row_count": len(ranking),
            "completed_count": len(completed_symbols),
            "failed_count": len(failures),
        },
        "elapsed_seconds": elapsed,
        "provider_requests": 0,
        "deferred_to_quick": [
            "Lower Standard Summary table", "Middle Standard Summary table", "Final Cross-Symbol Ranking",
            "Field 10/11", "AI/NLP", "research validation", "trust history", "institutional shadow layer",
        ],
        "persistence": persistence_status,
        "global_publication": publication_status,
        "result_tables": [
            "Regime Age Ranking — Candle After Regime Start Only",
            "Middle Regime Age Ranking — Candle After Middle Regime Start Only",
            "Higher Standard Summary",
        ],
        "reused_cached_calculation": False,
        "cache_signature": input_signature,
    }
    state["super_quick_field3_input_signature_20260727"] = input_signature
    state["super_quick_field3_cached_result_20260727"] = dict(result)
    state["settings_run_status_20260617"] = result
    return result


__all__ = ["FAST_RUN_VERSION", "run_super_quick_field3"]
