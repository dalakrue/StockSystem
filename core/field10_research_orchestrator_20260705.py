"""Heavy Settings-run orchestrator for the Field 10 shadow research candidate.

All calculations are performed from the immutable Field 10 parent snapshot and
exactly 600 completed same-symbol H1 candles.  The UI only reads the persisted
child evidence created here.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import (
    CANDIDATE_NAME, FEATURE_VERSION, FORMULA_VERSION, HORIZONS, MAX_SYMBOL_UNIVERSE,
    MODEL_VERSION, PROMOTION_STATUS, THRESHOLD_VERSION, audit_system_time,
    build_identity, canonical_json, connect, deterministic_hash, exact_completed_h1,
    exact_symbol_state, identity_columns, insert_or_ignore, load_snapshot_contract,
    normalize_symbol, schema_ready, completed_intraday_frame, finite,
)
from core.field10_har_semivariance_20260705 import har_h1_forecasts, realized_semivariance
from core.field10_gas_tailrisk_20260705 import bounded_gas_update, directional_var_es
from core.field10_fx_connectedness_20260705 import (
    FREQUENCY_MAPPING_VERSION, full_connectedness_bundle,
)
from core.field10_model_selection_20260705 import (
    CANDIDATE_MODELS, aggregate_split_robustness, candidate_registry_hash,
    chronological_sample_splits, model_confidence_set,
)
from core.field10_rank_utility_v2_20260705 import (
    FORMULA_THRESHOLD_REGISTRY, horizon_managed_utility, rank_shadow_candidates,
)

VERSION = "field10-research-orchestrator-20260705-v1"


def _decode(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except Exception:
        return default


def _probability_percent(value: Any) -> float | None:
    number = finite(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return float(np.clip(number, 0.0, 100.0))


def _parent_probability(parent: Mapping[str, Any], horizon: int) -> tuple[float | None, str]:
    direct = {
        1: "probability_profit_1h", 6: "probability_profit_6h", 12: "probability_profit_12h",
    }.get(horizon)
    if direct:
        value = _probability_percent(parent.get(direct))
        if value is not None:
            return value, str(parent.get("probability_calibration_status") or "PARENT_CALIBRATION_STATUS_UNSPECIFIED")
    row = _decode(parent.get("row_json"), {})
    aliases = (
        f"Calibrated Probability {horizon}H", f"Probability Profit {horizon}H",
        f"Probability {horizon}H", f"Probability of Profit {horizon}H",
    )
    for key in aliases:
        value = _probability_percent(row.get(key))
        if value is not None:
            return value, "PARENT_ROW_CALIBRATED_OR_REPORTED"
    return None, "UNAVAILABLE"


def _transition_risk(parent: Mapping[str, Any], horizon: int) -> tuple[float | None, str]:
    direct = {6: parent.get("transition_risk_6h"), 24: parent.get("transition_risk_24h")}.get(horizon)
    if finite(direct) is not None:
        return _probability_percent(direct), "PARENT_EXACT_HORIZON"
    row = _decode(parent.get("row_json"), {})
    for key in (f"Transition Risk {horizon}H", f"Transition Risk {horizon}h", f"transition_risk_{horizon}h"):
        value = _probability_percent(row.get(key))
        if value is not None:
            return value, "PARENT_EXACT_HORIZON"
    # Constant-hazard interpolation/extrapolation is explicit and versioned.
    anchors = []
    for h, raw in ((6, parent.get("transition_risk_6h")), (24, parent.get("transition_risk_24h"))):
        p = _probability_percent(raw)
        if p is not None and 0 <= p < 100:
            hourly_hazard = 1.0 - (1.0 - p / 100.0) ** (1.0 / h)
            anchors.append((abs(h - horizon), hourly_hazard, h))
    if not anchors:
        return None, "UNAVAILABLE"
    _, hazard, source_h = min(anchors)
    derived = 100.0 * (1.0 - (1.0 - hazard) ** horizon)
    return float(np.clip(derived, 0.0, 100.0)), f"CONSTANT_HAZARD_DERIVED_FROM_{source_h}H"


def _reliability(parent: Mapping[str, Any]) -> float | None:
    for value in (parent.get("institutional_score"), parent.get("existing_rank_score")):
        score = finite(value)
        if score is not None:
            return float(np.clip(score, 0.0, 100.0))
    row = _decode(parent.get("row_json"), {})
    for key in ("Reliability", "Reliability Score", "Final Reliability"):
        score = _probability_percent(row.get(key))
        if score is not None:
            return score
    return None


def _data_quality(parent: Mapping[str, Any], frame: pd.DataFrame, reasons: Sequence[str], semivariance: Mapping[str, Any]) -> float:
    completeness = 0.0 if frame.empty else float(frame[["open", "high", "low", "close"]].notna().mean().mean())
    score = 100.0 * completeness
    if reasons:
        score -= min(60.0, 12.0 * len(reasons))
    if str(semivariance.get("semivariance_method")) == "H1_SIGNED_VARIANCE_PROXY":
        score -= 15.0
    if not parent.get("source_id") or not parent.get("snapshot_hash"):
        score -= 20.0
    return float(np.clip(score, 0.0, 100.0))


def _exact_costs(state: Mapping[str, Any], symbol: str, completed_candle: str) -> tuple[float | None, float | None, str]:
    try:
        from core.field10_crowd_final_20260704 import extract_exact_completed_h1, _execution_cost_pct
        exact, reason = exact_symbol_state(state, symbol)
        if exact is None:
            return None, None, reason or "same-symbol state unavailable"
        frame, validation = extract_exact_completed_h1(exact, completed_candle, required=600)
        if validation.get("status") != "PASS":
            return None, None, str(validation.get("reason") or validation.get("status"))
        spread_pct = _execution_cost_pct(frame, "spread_raw")
        slippage_pct = _execution_cost_pct(frame, "slippage_raw")
        # Utility is in log-return units; source helper returns percentage units.
        return (
            None if spread_pct is None else float(spread_pct) / 100.0,
            None if slippage_pct is None else float(slippage_pct) / 100.0,
            "AVAILABLE" if spread_pct is not None and slippage_pct is not None else "MISSING_PROVIDER_COST_EVIDENCE",
        )
    except Exception as exc:
        return None, None, f"cost extraction failed: {type(exc).__name__}: {exc}"


def _previous_gas(path: Path | str, daily_snapshot_id: str, symbol: str) -> dict[str, float]:
    try:
        with connect(path, read_only=True) as conn:
            rows = conn.execute(
                "SELECT state_name,resulting_state FROM field10_gas_state_shadow "
                "WHERE symbol=? AND daily_snapshot_id<>? ORDER BY created_system_time DESC",
                (symbol, daily_snapshot_id),
            ).fetchall()
        output: dict[str, float] = {}
        for row in rows:
            if str(row[0]) not in output and finite(row[1]) is not None:
                output[str(row[0])] = float(row[1])
        return output
    except Exception:
        return {}


def _settled_loss_panel(path: Path | str, symbol: str, horizon: int) -> pd.DataFrame:
    """Read only chronologically settled forecast losses; never substitute in-sample losses."""
    try:
        with connect(path, read_only=True) as conn:
            rows = conn.execute(
                "SELECT f.completed_h1_candle,f.model_version,f.net_expected_value,f.expected_value,o.net_realized_return,o.realized_return "
                "FROM field10_forecast_ledger f JOIN field10_outcome_ledger o ON o.forecast_id=f.forecast_id "
                "WHERE f.symbol=? AND f.horizon_hours=? ORDER BY f.completed_h1_candle",
                (symbol, horizon),
            ).fetchall()
    except sqlite3.Error:
        return pd.DataFrame()
    model_aliases = {model: model for model in CANDIDATE_MODELS}
    records: list[dict[str, Any]] = []
    for row in rows:
        version = str(row[1] or "").lower()
        model = next((name for token, name in model_aliases.items() if token in version), None)
        if model is None:
            continue
        prediction = finite(row[2]) if finite(row[2]) is not None else finite(row[3])
        actual = finite(row[4]) if finite(row[4]) is not None else finite(row[5])
        if prediction is None or actual is None:
            continue
        records.append({"origin": str(row[0]), "model": model, "loss": abs(actual - prediction)})
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).pivot_table(index="origin", columns="model", values="loss", aggfunc="last").sort_index()


def _settlement_completeness(path: Path | str, symbol: str) -> float:
    try:
        with connect(path, read_only=True) as conn:
            totals = conn.execute(
                "SELECT COUNT(*),SUM(CASE WHEN o.forecast_id IS NOT NULL THEN 1 ELSE 0 END) "
                "FROM field10_forecast_ledger f LEFT JOIN field10_outcome_ledger o ON o.forecast_id=f.forecast_id WHERE f.symbol=?",
                (symbol,),
            ).fetchone()
        total = int(totals[0] or 0)
        settled = int(totals[1] or 0)
        return 0.0 if total == 0 else 100.0 * settled / total
    except sqlite3.Error:
        return 0.0


def _mapped_band(horizon: int) -> str:
    if horizon <= 6:
        return "short"
    if horizon <= 24:
        return "medium"
    return "persistent"


def _base(identity: Any, status: str, missing_reason: str | None, evidence: Mapping[str, Any]) -> dict[str, Any]:
    payload = identity_columns(identity, validation_status=status, missing_reason=missing_reason)
    payload["evidence_json"] = canonical_json(evidence)
    return payload


def _finalize(payload: dict[str, Any]) -> dict[str, Any]:
    core = {k: v for k, v in payload.items() if k != "content_hash"}
    payload["content_hash"] = deterministic_hash(core)
    return payload


def _persist(conn: sqlite3.Connection, table: str, payload: dict[str, Any]) -> int:
    return insert_or_ignore(conn, table, _finalize(payload))


def publish_horizon_connected_tail_candidate(
    state: MutableMapping[str, Any], *, daily_snapshot_id: str, selected_symbols: Sequence[str], path: Path | str,
) -> dict[str, Any]:
    ready, missing = schema_ready(path)
    if not ready:
        return {"ok": False, "status": "MIGRATION_REQUIRED", "missing_tables": missing, "runtime_migration_executed": False}
    meta, parents = load_snapshot_contract(daily_snapshot_id, path=path)
    if not meta or not parents:
        return {"ok": False, "status": "PARENT_SNAPSHOT_UNAVAILABLE", "daily_snapshot_id": daily_snapshot_id}
    requested = [normalize_symbol(v) for v in selected_symbols if normalize_symbol(v)]
    parent_symbols = [normalize_symbol(row.get("symbol")) for row in parents]
    if set(requested) != set(parent_symbols):
        return {"ok": False, "status": "IDENTITY_MISMATCH", "requested": requested, "parent": parent_symbols}
    if len(parent_symbols) > MAX_SYMBOL_UNIVERSE:
        return {"ok": False, "status": "UNIVERSE_LIMIT_EXCEEDED", "maximum": MAX_SYMBOL_UNIVERSE, "found": len(parent_symbols)}

    packs: dict[str, dict[str, Any]] = {}
    frames: dict[str, pd.DataFrame] = {}
    biases: dict[str, str] = {}
    for parent in parents:
        identity = build_identity(meta, parent, path=path)
        frame, reasons = exact_completed_h1(state, identity, required_rows=600)
        bias = str(parent.get("less_risky_bias") or parent.get("stable_daily_bias") or "WAIT").upper()
        biases[identity.symbol] = bias
        if not frame.empty and not reasons:
            frames[identity.symbol] = frame
        packs[identity.symbol] = {"parent": parent, "identity": identity, "frame": frame, "reasons": reasons, "bias": bias}

    connected = full_connectedness_bundle(frames, biases) if len(frames) >= 2 else {
        "copula": {"status": "INSUFFICIENT_PANEL", "pairs": [], "symbols": {}},
        "asymmetric": {"status": "INSUFFICIENT_PANEL", "symbols": {}},
        "frequency": {"status": "INSUFFICIENT_PANEL", "symbols": {}},
        "panel": pd.DataFrame(),
    }
    summary_inputs: list[dict[str, Any]] = []
    calculated: dict[str, dict[str, Any]] = {}

    for symbol, pack in packs.items():
        parent = pack["parent"]
        identity = pack["identity"]
        frame = pack["frame"]
        reasons = pack["reasons"]
        bias = pack["bias"]
        intraday, intraday_reason = completed_intraday_frame(state, identity)
        semivar = realized_semivariance(frame, intraday)
        transition6, transition6_method = _transition_risk(parent, 6)
        reliability = _reliability(parent)
        returns = np.log(pd.to_numeric(frame.get("close"), errors="coerce") / pd.to_numeric(frame.get("close"), errors="coerce").shift(1)) if not frame.empty else pd.Series(dtype=float)
        dependence_innovation = finite(connected.get("copula", {}).get("symbols", {}).get(symbol, {}).get("dependence_instability"))
        gas = bounded_gas_update(
            returns, previous_state=_previous_gas(path, daily_snapshot_id, symbol),
            dependence_innovation=dependence_innovation, transition_risk=transition6, reliability=reliability,
        )
        har = har_h1_forecasts(frame)
        tail = directional_var_es(frame, bias=bias, gas_result=gas)
        split_rows: list[dict[str, Any]] = []
        split_aggregate: dict[int, dict[str, dict[str, Any]]] = {}
        mcs_rows: dict[int, list[dict[str, Any]]] = {}
        for horizon in HORIZONS:
            rows = chronological_sample_splits(frame, bias=bias, horizon=horizon) if not frame.empty else []
            split_rows.extend(rows)
            split_aggregate[horizon] = aggregate_split_robustness(rows)
            mcs_rows[horizon] = model_confidence_set(
                _settled_loss_panel(path, symbol, horizon), seed_key=f"{identity.snapshot_hash}:{symbol}:{horizon}",
            )
        spread_cost, slippage_cost, cost_status = _exact_costs(state, symbol, identity.completed_h1_candle)
        asym = connected.get("asymmetric", {}).get("symbols", {}).get(symbol, {})
        freq = connected.get("frequency", {}).get("symbols", {}).get(symbol, {})
        cop = connected.get("copula", {}).get("symbols", {}).get(symbol, {})
        utility: dict[int, dict[str, Any]] = {}
        for horizon in HORIZONS:
            har_row = har.get("horizons", {}).get(horizon, {})
            tail_row = tail.get("horizons", {}).get(horizon, {})
            transition, transition_method = _transition_risk(parent, horizon)
            lower = finite(har_row.get("expected_movement_lower")); upper = finite(har_row.get("expected_movement_upper"))
            latest_close = finite(frame["close"].iloc[-1]) if not frame.empty else None
            interval_width = None if lower is None or upper is None or latest_close in (None, 0.0) else abs(upper - lower) / latest_close
            # Explicitly defined proxy based on independent available research estimates.
            disagreement_values = [
                finite(tail_row.get("tail_adjusted_expected_value")),
                finite(parent.get(f"expected_return_{horizon}h")),
                finite(parent.get(f"expected_value_{horizon}h")),
            ]
            disagreement_values = [v for v in disagreement_values if v is not None]
            model_disagreement = None if len(disagreement_values) < 2 else 100.0 * float(np.std(disagreement_values, ddof=0)) / max(abs(float(np.mean(disagreement_values))), 1e-8)
            utility[horizon] = horizon_managed_utility(
                frame, bias=bias, horizon=horizon,
                forecast_volatility=har_row.get("forecast_volatility"),
                expected_shortfall=tail_row.get("directional_expected_shortfall_95"),
                transition_risk_pct=transition,
                bad_spillover_pct=asym.get("adverse_connectedness_score"),
                prediction_interval_width=interval_width,
                model_disagreement=model_disagreement,
                spread_cost=spread_cost, slippage_cost=slippage_cost,
            )
            utility[horizon]["transition_method"] = transition_method
            utility[horizon]["model_disagreement_method"] = "INDEPENDENT_ESTIMATE_DISPERSION_PROXY" if model_disagreement is not None else "UNAVAILABLE"
            utility[horizon]["cost_evidence_status"] = cost_status
        calibrated, calibration_status = _parent_probability(parent, 6)
        if calibrated is None:
            proxy = finite(utility.get(6, {}).get("probability_win"))
            calibrated = None if proxy is None else 100.0 * proxy
            calibration_status = "HISTORICAL_DIRECTION_RATE_PROXY_NOT_CALIBRATED"
        weights = FORMULA_THRESHOLD_REGISTRY["horizon_weights"]
        managed_available = [(h, finite(utility[h].get("managed_utility"))) for h in HORIZONS]
        managed_available = [(h, v) for h, v in managed_available if v is not None]
        managed_weighted = None if not managed_available else sum(weights[h] * v for h, v in managed_available) / sum(weights[h] for h, _ in managed_available)
        target_split = split_aggregate.get(6, {}).get("connectedness_adjusted_model", {})
        mcs6 = mcs_rows.get(6, [])
        mcs_survivor = next((r for r in mcs6 if r.get("model_name") == "connectedness_adjusted_model"), {})
        data_quality = _data_quality(parent, frame, reasons, semivar)
        if calibration_status.startswith("HISTORICAL"):
            data_quality = max(0.0, data_quality - 10.0)
        summary = {
            "symbol": symbol, "production_rank": parent.get("daily_rank"), "locked_bias": bias,
            "entry_permission": "BLOCK" if gas.get("entry_permission") == "BLOCK" or asym.get("contagion_safety_permission") == "BLOCK" else "CAUTION" if gas.get("entry_permission") == "CAUTION" or asym.get("contagion_safety_permission") == "CAUTION" else "SHADOW_UNCHANGED",
            "calibrated_probability": calibrated, "calibration_status": calibration_status,
            "managed_utility_weighted": managed_weighted,
            "managed_utility_6h": utility.get(6, {}).get("managed_utility"),
            "managed_utility_12h": utility.get(12, {}).get("managed_utility"),
            "expected_shortfall_95": tail.get("horizons", {}).get(6, {}).get("directional_expected_shortfall_95"),
            "transition_risk_6h": transition6,
            "adverse_semivariance_pressure": semivar.get("buy_directional_tail_pressure") if bias == "BUY" else semivar.get("sell_directional_tail_pressure") if bias == "SELL" else None,
            "adverse_connectedness_score": asym.get("adverse_connectedness_score"),
            "persistent_connectedness": freq.get("connectedness_persistent"),
            "tail_crowding_penalty": cop.get("tail_crowding_penalty"),
            "duplicate_exposure_penalty": cop.get("duplicate_exposure_penalty"),
            "volatility_safety": utility.get(6, {}).get("volatility_safety"),
            "regime_stability": None if transition6 is None else 100.0 - transition6,
            "mcs_membership_score": 100.0 if mcs_survivor.get("mcs_membership") else 0.0,
            "mcs_status": mcs_survivor.get("mcs_status") or "INSUFFICIENT_SETTLED_OOS_LOSSES",
            "split_robustness_score": target_split.get("split_robustness_score"),
            "split_stability_permission": target_split.get("split_stability_permission") or "BLOCK",
            "data_quality_score": data_quality,
            "settlement_completeness": _settlement_completeness(path, symbol),
            "reliability": reliability,
            "identity_valid": not reasons and len(frame) == 600,
            "missing_reasons": list(reasons) + ([intraday_reason] if intraday_reason else []),
            "promotion_status": PROMOTION_STATUS,
        }
        summary_inputs.append(summary)
        calculated[symbol] = {
            **pack, "har": har, "semivariance": semivar, "gas": gas, "tail": tail,
            "split_rows": split_rows, "split_aggregate": split_aggregate, "mcs_rows": mcs_rows,
            "utility": utility, "summary": summary,
        }

    rank_result = rank_shadow_candidates(summary_inputs, seed_key=str(meta.get("snapshot_hashes_json") or meta.get("content_hash") or daily_snapshot_id))
    ranked_map = {str(row["symbol"]): row for row in rank_result.get("rows", [])}
    component_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rank_result.get("components", []):
        component_by_symbol.setdefault(str(row.get("symbol")), []).append(row)

    inserted = {table: 0 for table in (
        "field10_horizon_volatility_shadow", "field10_semivariance_shadow", "field10_gas_state_shadow",
        "field10_tail_risk_shadow", "field10_copula_shadow", "field10_connectedness_shadow",
        "field10_frequency_connectedness_shadow", "field10_model_confidence_set",
        "field10_sample_split_validation", "field10_rank_components_v2",
    )}
    created = audit_system_time()
    with connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Pair evidence is stored once under deterministic lexical pair ownership.
            for pair in connected.get("copula", {}).get("pairs", []):
                owner = min(str(pair["symbol"]), str(pair["peer_symbol"]))
                pack = calculated.get(owner)
                if not pack:
                    continue
                identity = pack["identity"]
                payload = _base(identity, str(pair.get("copula_validation_status") or "UNAVAILABLE"), None, pair)
                payload.update({
                    "peer_symbol": max(str(pair["symbol"]), str(pair["peer_symbol"])), "horizon": 1,
                    "ordinary_conditional_dependence": pair.get("ordinary_conditional_dependence"),
                    "lower_tail_dependence": pair.get("lower_tail_dependence"), "upper_tail_dependence": pair.get("upper_tail_dependence"),
                    "joint_adverse_move_probability": pair.get("joint_adverse_move_probability"),
                    "joint_favorable_move_probability": pair.get("joint_favorable_move_probability"),
                    "dependence_regime": pair.get("dependence_regime"), "dependence_instability": pair.get("dependence_instability"),
                    "duplicate_currency_exposure": pair.get("duplicate_currency_exposure"),
                    "currency_leg_detail_json": canonical_json(pair.get("currency_leg_detail") or {}),
                    "copula_validation_status": pair.get("copula_validation_status") or "UNAVAILABLE",
                    "sample_count": int(pair.get("sample_count") or 0), "created_system_time": created,
                })
                inserted["field10_copula_shadow"] += _persist(conn, "field10_copula_shadow", payload)

            for symbol, pack in calculated.items():
                identity = pack["identity"]; har = pack["har"]; semivar = pack["semivariance"]; gas = pack["gas"]; tail = pack["tail"]
                summary = ranked_map.get(symbol, pack["summary"])
                asym = connected.get("asymmetric", {}).get("symbols", {}).get(symbol, {})
                freq = connected.get("frequency", {}).get("symbols", {}).get(symbol, {})
                for horizon in HORIZONS:
                    har_row = har.get("horizons", {}).get(horizon, {})
                    payload = _base(identity, str(har_row.get("har_validation_status") or "UNAVAILABLE"), har_row.get("har_missing_reason"), har_row)
                    payload.update({
                        "horizon": horizon, "forecast_volatility": har_row.get("forecast_volatility"),
                        "volatility_percentile": har_row.get("volatility_percentile"), "volatility_surprise": har_row.get("volatility_surprise"),
                        "volatility_forecast_error": har_row.get("volatility_forecast_error"),
                        "expected_movement_lower": har_row.get("expected_movement_lower"), "expected_movement_upper": har_row.get("expected_movement_upper"),
                        "har_sample_count": int(har_row.get("har_sample_count") or 0),
                        "har_validation_status": har_row.get("har_validation_status") or "UNAVAILABLE", "har_missing_reason": har_row.get("har_missing_reason"),
                        "created_system_time": created,
                    })
                    inserted["field10_horizon_volatility_shadow"] += _persist(conn, "field10_horizon_volatility_shadow", payload)

                    tail_row = tail.get("horizons", {}).get(horizon, {})
                    payload = _base(identity, str(tail_row.get("tail_backtest_status") or tail_row.get("status") or "UNAVAILABLE"), tail_row.get("missing_reason"), tail_row)
                    payload.update({
                        "horizon": horizon, "direction": pack["bias"], "directional_var_95": tail_row.get("directional_var_95"),
                        "directional_expected_shortfall_95": tail_row.get("directional_expected_shortfall_95"),
                        "es_var_severity_ratio": tail_row.get("es_var_severity_ratio"), "tail_loss_probability": tail_row.get("tail_loss_probability"),
                        "tail_adjusted_expected_value": tail_row.get("tail_adjusted_expected_value"), "tail_model_coverage": tail_row.get("tail_model_coverage"),
                        "tail_exception_count": tail_row.get("tail_exception_count"), "tail_exception_total": tail_row.get("tail_exception_total"),
                        "tail_exception_independence": tail_row.get("tail_exception_independence"), "joint_var_es_loss": tail_row.get("joint_var_es_loss"),
                        "tail_backtest_status": tail_row.get("tail_backtest_status") or tail_row.get("status") or "UNAVAILABLE",
                        "purge_hours": int(tail_row.get("purge_hours") or horizon), "embargo_hours": int(tail_row.get("embargo_hours") or horizon),
                        "created_system_time": created,
                    })
                    inserted["field10_tail_risk_shadow"] += _persist(conn, "field10_tail_risk_shadow", payload)

                    band = _mapped_band(horizon)
                    payload = _base(identity, str(freq.get("horizon_connectedness_status") or connected.get("frequency", {}).get("status") or "UNAVAILABLE"), None, {**freq, "mapping": connected.get("frequency", {}).get("mapping")})
                    payload.update({
                        "horizon": horizon, "connectedness_short": freq.get("connectedness_short"),
                        "connectedness_medium": freq.get("connectedness_medium"), "connectedness_persistent": freq.get("connectedness_persistent"),
                        "mapped_connectedness": freq.get(f"connectedness_{band}"), "mapped_band": band,
                        "persistent_shock_share": freq.get("persistent_shock_share"),
                        "short_horizon_net_transmitter": freq.get("short_horizon_net_transmitter"),
                        "medium_horizon_net_transmitter": freq.get("medium_horizon_net_transmitter"),
                        "persistent_net_transmitter": freq.get("persistent_net_transmitter"),
                        "horizon_connectedness_status": freq.get("horizon_connectedness_status") or "UNAVAILABLE",
                        "frequency_mapping_version": FREQUENCY_MAPPING_VERSION, "created_system_time": created,
                    })
                    inserted["field10_frequency_connectedness_shadow"] += _persist(conn, "field10_frequency_connectedness_shadow", payload)

                    for mcs in pack["mcs_rows"].get(horizon, []):
                        payload = _base(identity, str(mcs.get("mcs_status") or "UNAVAILABLE"), None if mcs.get("mean_loss") is not None else "insufficient settled out-of-sample loss panel", mcs)
                        payload.update({
                            "horizon": horizon, "model_name": mcs.get("model_name"), "loss_function": "ABSOLUTE_FORECAST_ERROR",
                            "mean_loss": mcs.get("mean_loss"), "mcs_membership": int(bool(mcs.get("mcs_membership"))),
                            "elimination_round": mcs.get("elimination_round"), "test_statistic": mcs.get("test_statistic"), "p_value": mcs.get("p_value"),
                            "validation_window": "SETTLED_OUT_OF_SAMPLE_ONLY", "bootstrap_draws": int(mcs.get("bootstrap_draws") or 500),
                            "block_length": int(mcs.get("block_length") or 12), "model_weight": mcs.get("model_weight"),
                            "mcs_status": mcs.get("mcs_status") or "UNAVAILABLE", "candidate_registry_hash": candidate_registry_hash(),
                            "created_system_time": created,
                        })
                        inserted["field10_model_confidence_set"] += _persist(conn, "field10_model_confidence_set", payload)

                sem_status = str(semivar.get("semivariance_validation_status") or "UNAVAILABLE")
                payload = _base(identity, sem_status, semivar.get("missing_reason"), {k: v for k, v in semivar.items() if k != "series"})
                payload.update({
                    "horizon": 1, "positive_realized_semivariance": semivar.get("positive_realized_semivariance"),
                    "negative_realized_semivariance": semivar.get("negative_realized_semivariance"), "downside_share": semivar.get("downside_share"),
                    "upside_share": semivar.get("upside_share"), "semivariance_imbalance": semivar.get("semivariance_imbalance"),
                    "buy_directional_tail_pressure": semivar.get("buy_directional_tail_pressure"), "sell_directional_tail_pressure": semivar.get("sell_directional_tail_pressure"),
                    "semivariance_method": semivar.get("semivariance_method") or "UNAVAILABLE", "semivariance_sample_count": int(semivar.get("semivariance_sample_count") or 0),
                    "semivariance_validation_status": sem_status, "reliability_penalty": 15.0 if semivar.get("semivariance_method") == "H1_SIGNED_VARIANCE_PROXY" else 0.0,
                    "created_system_time": created,
                })
                inserted["field10_semivariance_shadow"] += _persist(conn, "field10_semivariance_shadow", payload)

                for state_name, state_row in (gas.get("states") or {}).items():
                    payload = _base(identity, "AVAILABLE" if state_row.get("finite_validation") and state_row.get("bound_validation") else "INVALID", None, state_row)
                    payload.update({
                        "horizon": 1, "state_name": state_name, "previous_state": state_row.get("previous_state"), "scaled_score": state_row.get("scaled_score"),
                        "omega": state_row.get("omega"), "score_loading": state_row.get("score_loading"), "persistence": state_row.get("persistence"),
                        "update_magnitude": state_row.get("update_magnitude"), "resulting_state": state_row.get("resulting_state"),
                        "lower_bound": state_row.get("lower_bound"), "upper_bound": state_row.get("upper_bound"),
                        "finite_validation": int(bool(state_row.get("finite_validation"))), "bound_validation": int(bool(state_row.get("bound_validation"))),
                        "created_system_time": created,
                    })
                    inserted["field10_gas_state_shadow"] += _persist(conn, "field10_gas_state_shadow", payload)

                payload = _base(identity, str(connected.get("asymmetric", {}).get("status") or "UNAVAILABLE"), None, asym)
                payload.update({
                    "horizon": 12, "bad_volatility_received": asym.get("bad_volatility_received"), "bad_volatility_transmitted": asym.get("bad_volatility_transmitted"),
                    "good_volatility_received": asym.get("good_volatility_received"), "good_volatility_transmitted": asym.get("good_volatility_transmitted"),
                    "net_bad_spillover": asym.get("net_bad_volatility_spillover"), "net_good_spillover": asym.get("net_good_volatility_spillover"),
                    "stress_receiver_status": asym.get("stress_receiver_status"), "stress_transmitter_status": asym.get("stress_transmitter_status"),
                    "adverse_connectedness_score": asym.get("adverse_connectedness_score"),
                    "contagion_safety_permission": asym.get("contagion_safety_permission") or "BLOCK_UNAVAILABLE", "created_system_time": created,
                })
                inserted["field10_connectedness_shadow"] += _persist(conn, "field10_connectedness_shadow", payload)

                for split in pack["split_rows"]:
                    payload = _base(identity, "PASS" if split.get("split_pass") else "REVIEW", None, split)
                    payload.update({
                        "horizon": int(split.get("horizon")), "model_name": split.get("model_name"), "split_id": split.get("split_id"),
                        "training_start": split.get("training_start"), "training_end": split.get("training_end"),
                        "validation_start": split.get("validation_start"), "validation_end": split.get("validation_end"),
                        "test_start": split.get("test_start"), "test_end": split.get("test_end"),
                        "out_of_sample_loss": split.get("out_of_sample_loss"), "calibration_error": split.get("calibration_error"),
                        "coverage_error": split.get("coverage_error"), "net_expected_value_error": split.get("net_expected_value_error"),
                        "split_rank": split.get("split_rank"), "split_pass": int(bool(split.get("split_pass"))),
                        "purge_hours": int(split.get("purge_hours") or split.get("horizon")), "embargo_hours": int(split.get("embargo_hours") or split.get("horizon")),
                        "candidate_registered_before_test": int(bool(split.get("candidate_registered_before_test"))), "created_system_time": created,
                    })
                    inserted["field10_sample_split_validation"] += _persist(conn, "field10_sample_split_validation", payload)

                summary_payload = _base(identity, "SHADOW_ONLY", None, summary)
                summary_payload.update({
                    "horizon": 0, "component_name": "__SUMMARY__", "raw_value": summary.get("shadow_score"), "normalized_score": None,
                    "configured_weight": None, "duplicate_penalty": None, "effective_weight": None, "weighted_contribution": None,
                    "shadow_score": summary.get("shadow_score"), "shadow_rank": summary.get("shadow_rank"), "production_rank": summary.get("production_rank"),
                    "locked_bias": summary.get("locked_bias"), "entry_permission": summary.get("entry_permission"),
                    "managed_utility_6h": summary.get("managed_utility_6h"), "managed_utility_12h": summary.get("managed_utility_12h"),
                    "expected_shortfall_95": summary.get("expected_shortfall_95"), "transition_risk_6h": summary.get("transition_risk_6h"),
                    "bad_connectedness": summary.get("adverse_connectedness_score"), "persistent_connectedness": summary.get("persistent_connectedness"),
                    "volatility_safety": summary.get("volatility_safety"), "mcs_status": summary.get("mcs_status"),
                    "split_robustness": summary.get("split_robustness_score"), "reliability": summary.get("reliability"),
                    "data_quality": summary.get("data_quality_score"), "rank_evidence_fraction": summary.get("rank_evidence_fraction"),
                    "promotion_status": PROMOTION_STATUS, "summary_json": canonical_json(summary), "created_system_time": created,
                })
                inserted["field10_rank_components_v2"] += _persist(conn, "field10_rank_components_v2", summary_payload)
                for component in component_by_symbol.get(symbol, []):
                    payload = _base(identity, "SHADOW_COMPONENT", None, component)
                    payload.update({
                        "horizon": 0, "component_name": component.get("component_name"), "raw_value": component.get("raw_value"),
                        "normalized_score": component.get("normalized_score"), "configured_weight": component.get("configured_weight"),
                        "duplicate_penalty": component.get("duplicate_penalty"), "effective_weight": component.get("effective_weight"),
                        "weighted_contribution": component.get("weighted_contribution"), "shadow_score": summary.get("shadow_score"),
                        "shadow_rank": summary.get("shadow_rank"), "production_rank": summary.get("production_rank"), "locked_bias": summary.get("locked_bias"),
                        "entry_permission": summary.get("entry_permission"), "managed_utility_6h": summary.get("managed_utility_6h"),
                        "managed_utility_12h": summary.get("managed_utility_12h"), "expected_shortfall_95": summary.get("expected_shortfall_95"),
                        "transition_risk_6h": summary.get("transition_risk_6h"), "bad_connectedness": summary.get("adverse_connectedness_score"),
                        "persistent_connectedness": summary.get("persistent_connectedness"), "volatility_safety": summary.get("volatility_safety"),
                        "mcs_status": summary.get("mcs_status"), "split_robustness": summary.get("split_robustness_score"),
                        "reliability": summary.get("reliability"), "data_quality": summary.get("data_quality_score"),
                        "rank_evidence_fraction": summary.get("rank_evidence_fraction"), "promotion_status": PROMOTION_STATUS,
                        "summary_json": canonical_json(summary), "created_system_time": created,
                    })
                    inserted["field10_rank_components_v2"] += _persist(conn, "field10_rank_components_v2", payload)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # Publish the additive v3 rank candidate from the same immutable snapshot
    # and already-computed heavy evidence. A missing v3 deployment migration is
    # diagnostic only and cannot invalidate or alter the existing v2 publication.
    try:
        from core.field10_v3_candidate_orchestrator_20260705 import publish_field10_rank_utility_v3_candidate
        v3_candidate_report = publish_field10_rank_utility_v3_candidate(
            state, daily_snapshot_id=daily_snapshot_id, selected_symbols=parent_symbols,
            path=path, precomputed={"calculated": calculated, "connected": connected},
        )
    except Exception as v3_exc:
        v3_candidate_report = {
            "ok": False, "status": "FAILED", "candidate": "field10-rank-utility-v3-research-candidate",
            "error": f"{type(v3_exc).__name__}: {v3_exc}",
            "production_rank_modified": False, "locked_bias_modified": False,
        }

    return {
        "ok": True,
        "status": "PUBLISHED_SHADOW_ONLY",
        "candidate": CANDIDATE_NAME,
        "promotion_status": PROMOTION_STATUS,
        "daily_snapshot_id": daily_snapshot_id,
        "parent_run_id": meta.get("parent_run_id"),
        "symbols": parent_symbols,
        "inserted": inserted,
        "production_rank_modified": False,
        "locked_bias_modified": False,
        "runtime_migration_executed": False,
        "horizon_independence": all(pack["har"].get("horizon_independence") for pack in calculated.values() if pack["frame"] is not None and len(pack["frame"]) == 600),
        "frequency_mapping_version": FREQUENCY_MAPPING_VERSION,
        "candidate_registry_hash": candidate_registry_hash(),
        "rank_utility_v3_candidate": v3_candidate_report,
        "version": VERSION,
    }


def load_candidate_summary(daily_snapshot_id: str | None = None, *, path: Path | str) -> pd.DataFrame:
    ready, _ = schema_ready(path)
    if not ready:
        return pd.DataFrame()
    with connect(path, read_only=True) as conn:
        if not daily_snapshot_id:
            found = conn.execute(
                "SELECT daily_snapshot_id FROM field10_rank_components_v2 WHERE component_name='__SUMMARY__' ORDER BY created_system_time DESC LIMIT 1"
            ).fetchone()
            daily_snapshot_id = None if found is None else str(found[0])
        if not daily_snapshot_id:
            return pd.DataFrame()
        return pd.read_sql_query(
            "SELECT * FROM field10_rank_components_v2 WHERE daily_snapshot_id=? AND component_name='__SUMMARY__' ORDER BY production_rank IS NULL,production_rank,symbol",
            conn, params=(daily_snapshot_id,),
        )


def load_candidate_details(daily_snapshot_id: str, *, path: Path | str) -> dict[str, pd.DataFrame]:
    ready, _ = schema_ready(path)
    if not ready or not daily_snapshot_id:
        return {}
    tables = (
        "field10_horizon_volatility_shadow", "field10_semivariance_shadow", "field10_gas_state_shadow",
        "field10_tail_risk_shadow", "field10_copula_shadow", "field10_connectedness_shadow",
        "field10_frequency_connectedness_shadow", "field10_model_confidence_set",
        "field10_sample_split_validation", "field10_rank_components_v2",
    )
    result: dict[str, pd.DataFrame] = {}
    with connect(path, read_only=True) as conn:
        for table in tables:
            result[table] = pd.read_sql_query(f"SELECT * FROM {table} WHERE daily_snapshot_id=?", conn, params=(daily_snapshot_id,))
    return result


__all__ = ["VERSION", "publish_horizon_connected_tail_candidate", "load_candidate_summary", "load_candidate_details"]
