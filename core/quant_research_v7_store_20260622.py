"""One-shot V7 orchestrator and normalized atomic persistence bundle."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping
import gc
import json
import sqlite3
import time
import tracemalloc

import numpy as np
import pandas as pd

from core.quant_research_v7_contract_20260622 import (
    MAX_H1_ROWS, MAX_M1_ROWS, METHOD_COUNT, VERSION, canonical_identity, common_method,
    json_safe, normalize_completed_frame, normalize_settled, stable_hash,
)
from services.canonical_snapshot_store import DB_PATH

BUNDLE_KEY = "__quant_research_v7__"
MIGRATION_PATH = Path(__file__).resolve().parents[1] / "migrations" / "20260622_quant_research_v7.sql"
TABLES = (
    "quant_research_v7_run", "quant_research_v7_method_results", "quant_research_v7_feature_stability",
    "quant_research_v7_bootstrap_results", "quant_research_v7_covariance_state", "quant_research_v7_dcc_state",
    "quant_research_v7_gas_state", "quant_research_v7_hsmm_duration", "quant_research_v7_midas_summary",
    "quant_research_v7_bds_tests", "quant_research_v7_trading_advisory", "quant_research_v7_coherent_risk",
    "quant_research_v7_error_history",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    buffer: list[str] = []
    for line in MIGRATION_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        statement = "\n".join(buffer).strip()
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            buffer = []
    if buffer:
        raise sqlite3.OperationalError("incomplete V7 migration")


def _json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _insert(conn: sqlite3.Connection, table: str, rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    inserted = ignored = 0
    for raw in rows:
        row = dict(raw)
        if not row:
            continue
        columns = list(row)
        cursor = conn.execute(
            f"INSERT OR IGNORE INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
            [row[column] for column in columns],
        )
        inserted += int(cursor.rowcount > 0)
        ignored += int(cursor.rowcount <= 0)
    return {"inserted": inserted, "idempotent_ignored": ignored}


def insert_quant_v7_bundle(conn: sqlite3.Connection, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
    ensure_schema(conn)
    return {table: _insert(conn, table, bundle.get(table, [])) for table in TABLES}


def _method_metrics(result: Mapping[str, Any], method_id: str) -> Mapping[str, Any]:
    method = result.get("methods", {}).get(method_id, {}) if isinstance(result.get("methods"), Mapping) else {}
    return method.get("output_metrics", {}) if isinstance(method, Mapping) and isinstance(method.get("output_metrics"), Mapping) else {}


def build_bundle(result: Mapping[str, Any], errors: list[Mapping[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    identity = result["identity"]; summary = result["summary"]; performance = result["performance"]
    calc = identity["calculation_id"]; generation = identity["source_generation_id"]; event = identity["latest_completed_h1_utc"]
    common = {"calculation_id": calc, "generation_id": generation, "event_time_utc": event}
    bundle = {table: [] for table in TABLES}
    bundle["quant_research_v7_run"].append({**common, "completed_broker_time": identity.get("completed_broker_time"), "status": summary["overall_status"], "method_count": METHOD_COUNT, "available_method_count": summary["available_method_count"], "sample_count": summary["sample_count"], "runtime_ms": performance.get("wall_time_ms"), "peak_traced_memory_mb": performance.get("peak_traced_memory_mb"), "serialized_result_bytes": performance.get("serialized_result_bytes"), "logic_version": VERSION, "payload_json": _json({"summary": summary, "performance": performance})})
    for method_id, method in result.get("methods", {}).items():
        bundle["quant_research_v7_method_results"].append({**common, "method_id": method_id, "paper_title": method.get("paper_title"), "status": method.get("status"), "sample_count": int(method.get("sample_count") or 0), "minimum_sample_required": int(method.get("minimum_sample_required") or 0), "logic_version": VERSION, "payload_json": _json(method)})
    stability = _method_metrics(result, "stability_selection")
    for rank, (feature, probability) in enumerate((stability.get("overall_selection_probability") or {}).items(), 1):
        bundle["quant_research_v7_feature_stability"].append({**common, "feature_name": str(feature), "selection_probability": probability, "rank_index": rank, "status": result["methods"]["stability_selection"].get("status"), "logic_version": VERSION})
    bootstrap = _method_metrics(result, "stationary_bootstrap")
    bundle["quant_research_v7_bootstrap_results"].append({**common, "result_key": "PRIMARY_MEAN", "replication_count": bootstrap.get("replication_count"), "mean_block_length": bootstrap.get("mean_block_length"), "confidence_level": bootstrap.get("confidence_level"), "seed_hash": bootstrap.get("seed_hash"), "status": bootstrap.get("status"), "logic_version": VERSION, "payload_json": _json(bootstrap)})
    cov = _method_metrics(result, "ledoit_wolf_covariance")
    bundle["quant_research_v7_covariance_state"].append({**common, "shrinkage_intensity": cov.get("shrinkage_intensity"), "raw_condition_number": cov.get("raw_condition_number"), "shrunk_condition_number": cov.get("shrunk_condition_number"), "positive_semidefinite": int(bool(cov.get("positive_semidefinite_status"))), "status": result["methods"]["ledoit_wolf_covariance"].get("status"), "logic_version": VERSION, "payload_json": _json(cov)})
    dcc = _method_metrics(result, "dynamic_conditional_correlation")
    bundle["quant_research_v7_dcc_state"].append({**common, "current_correlation": dcc.get("current_conditional_correlation"), "correlation_shock": dcc.get("correlation_shock"), "diversification_loss_score": dcc.get("diversification_loss_score"), "conflict_state": dcc.get("cross_market_conflict_state"), "status": result["methods"]["dynamic_conditional_correlation"].get("status"), "logic_version": VERSION, "payload_json": _json(dcc)})
    gas = _method_metrics(result, "generalized_autoregressive_score")
    bundle["quant_research_v7_gas_state"].append({**common, "current_error_scale": gas.get("current_error_scale"), "suggested_uncertainty_multiplier": gas.get("suggested_uncertainty_multiplier"), "tail_warning_state": gas.get("tail_warning_state"), "status": result["methods"]["generalized_autoregressive_score"].get("status"), "logic_version": VERSION, "payload_json": _json(gas)})
    hsmm = _method_metrics(result, "hidden_semi_markov_duration"); survival = hsmm.get("survival_probability") or {}
    bundle["quant_research_v7_hsmm_duration"].append({**common, "current_regime": hsmm.get("current_regime"), "current_age": hsmm.get("current_regime_age"), "expected_total_duration": hsmm.get("expected_total_duration"), "survival_h1": survival.get("H+1"), "survival_h6": survival.get("H+6"), "next_regime": hsmm.get("most_likely_next_regime"), "status": result["methods"]["hidden_semi_markov_duration"].get("status"), "logic_version": VERSION, "payload_json": _json(hsmm)})
    midas = _method_metrics(result, "midas_multi_frequency")
    bundle["quant_research_v7_midas_summary"].append({**common, "latest_m1_time": midas.get("latest_m1_time"), "return_pressure": midas.get("m1_return_pressure"), "directional_consistency": midas.get("m1_directional_consistency"), "realized_volatility": midas.get("m1_realized_volatility"), "status": result["methods"]["midas_multi_frequency"].get("status"), "logic_version": VERSION, "payload_json": _json(midas)})
    bds = _method_metrics(result, "bds_residual_test")
    for test in bds.get("tests", [])[:24]:
        bundle["quant_research_v7_bds_tests"].append({**common, "test_key": str(test.get("test_key") or stable_hash(test)), "embedding_dimension": test.get("embedding_dimension"), "epsilon_multiplier": test.get("epsilon_multiplier"), "statistic": test.get("statistic"), "raw_p_value": test.get("raw_p_value"), "adjusted_decision": test.get("adjusted_decision"), "status": result["methods"]["bds_residual_test"].get("status"), "logic_version": VERSION, "payload_json": _json(test)})
    trading = _method_metrics(result, "dynamic_trading_costs")
    bundle["quant_research_v7_trading_advisory"].append({**common, "advisory_label": trading.get("advisory_label"), "urgency": trading.get("urgency"), "turnover_warning": trading.get("turnover_warning"), "order_placement": int(bool(trading.get("order_placement"))), "status": result["methods"]["dynamic_trading_costs"].get("status"), "logic_version": VERSION, "payload_json": _json(trading)})
    risk = _method_metrics(result, "coherent_risk")
    bundle["quant_research_v7_coherent_risk"].append({**common, "risk_score": risk.get("shadow_coherent_risk_score"), "risk_budget": risk.get("bounded_risk_budget"), "risk_state": risk.get("final_shadow_risk_state"), "coherence_status": risk.get("coherence_test_status"), "shadow_tradeability": risk.get("shadow_tradeability"), "status": result["methods"]["coherent_risk"].get("status"), "logic_version": VERSION, "payload_json": _json(risk)})
    for error in errors or []:
        bundle["quant_research_v7_error_history"].append({"error_key": stable_hash([calc, generation, error])[:40], **common, "method_id": error.get("method_id"), "error_type": error.get("error_type"), "error_message": str(error.get("error_message"))[:1000], "failed_safely": 1, "logic_version": VERSION})
    return bundle


def _method_fail(method_id: str, cutoff: Any, exc: Exception) -> dict[str, Any]:
    return common_method(method_id, status="FAILED_SAFELY", sample_count=0, minimum_sample_required=0, cutoff_time=cutoff, output_metrics={"error_type": type(exc).__name__, "error_message": str(exc)[:300]}, assumptions=[], limitations=["optional V7 method failed safely"])


def _filter_market(market_history: pd.DataFrame | None, symbol: str, timeframe: str) -> pd.DataFrame:
    if not isinstance(market_history, pd.DataFrame) or market_history.empty:
        return pd.DataFrame()
    lower = {str(c).lower(): c for c in market_history.columns}
    if "symbol" not in lower or "timeframe" not in lower:
        return pd.DataFrame()
    mask = market_history[lower["symbol"]].astype(str).str.upper().eq(symbol.upper()) & market_history[lower["timeframe"]].astype(str).str.upper().eq(timeframe.upper())
    return market_history.loc[mask].copy(deep=False)


def build_quant_research_v7_transaction(
    canonical: Mapping[str, Any],
    completed_h1: pd.DataFrame,
    completed_m1: pd.DataFrame | None,
    settled_outcomes: pd.DataFrame | None,
    metric_history: pd.DataFrame | None,
    market_history: pd.DataFrame | None,
    state: MutableMapping[str, Any],
    previous: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build all V7 methods once and return canonical, one staged bundle, status."""
    output = deepcopy(dict(canonical or {})); previous = dict(previous or {})
    started = time.perf_counter(); tracemalloc.start(); errors: list[dict[str, Any]] = []; method_runtimes: dict[str, float] = {}
    try:
        cutoff = output.get("latest_completed_h1_utc") or output.get("latest_completed_candle_time")
        h1, h1_meta = normalize_completed_frame(completed_h1, cutoff_utc=cutoff, max_rows=MAX_H1_ROWS)
        if h1.empty:
            raise ValueError("canonical completed H1 evidence is unavailable")
        identity = canonical_identity(output, h1_meta); cutoff = identity["latest_completed_h1_utc"]
        market = market_history if isinstance(market_history, pd.DataFrame) else pd.DataFrame()
        m1_source = completed_m1 if isinstance(completed_m1, pd.DataFrame) and not completed_m1.empty else _filter_market(market, "EURUSD", "M1")
        m1, m1_meta = normalize_completed_frame(m1_source, cutoff_utc=cutoff, max_rows=MAX_M1_ROWS, required_ohlc=False) if isinstance(m1_source, pd.DataFrame) and not m1_source.empty else (pd.DataFrame(), {"rows": 0, "status": "UNAVAILABLE"})
        settled = normalize_settled(settled_outcomes, cutoff_utc=cutoff)
        history = metric_history.copy(deep=False) if isinstance(metric_history, pd.DataFrame) else pd.DataFrame()
        from core.quant_research_v7_stationary_bootstrap_20260622 import StationaryBootstrapService, run_stationary_bootstrap
        bootstrap_service = StationaryBootstrapService(identity["source_generation_id"])
        close_col = next((c for c in h1.columns if str(c).lower() == "close"), None)
        returns = pd.to_numeric(h1[close_col], errors="coerce").pct_change().dropna().to_numpy() if close_col else np.asarray([])
        runners = []
        from core.quant_research_v7_stability_selection_20260622 import run_stability_selection
        from core.quant_research_v7_covariance_dcc_20260622 import run_ledoit_wolf_covariance, run_dynamic_conditional_correlation
        from core.quant_research_v7_gas_20260622 import run_gas
        from core.quant_research_v7_hsmm_20260622 import run_hsmm
        from core.quant_research_v7_midas_20260622 import run_midas
        from core.quant_research_v7_bds_20260622 import run_bds
        from core.quant_research_v7_dynamic_trading_20260622 import run_dynamic_trading
        from core.quant_research_v7_coherent_risk_20260622 import run_coherent_risk
        methods: dict[str, Any] = {}
        def execute(method_id: str, fn) -> None:
            tick = time.perf_counter()
            try:
                methods[method_id] = fn()
            except Exception as exc:
                methods[method_id] = _method_fail(method_id, cutoff, exc)
                errors.append({"method_id": method_id, "error_type": type(exc).__name__, "error_message": str(exc)})
            method_runtimes[method_id] = round((time.perf_counter() - tick) * 1000.0, 3)
        execute("stability_selection", lambda: run_stability_selection(h1, generation_id=identity["source_generation_id"], cutoff_time=cutoff, canonical=output))
        execute("stationary_bootstrap", lambda: run_stationary_bootstrap(returns, generation_id=identity["source_generation_id"], cutoff_time=cutoff))
        execute("ledoit_wolf_covariance", lambda: run_ledoit_wolf_covariance(settled, market, cutoff_time=cutoff))
        execute("dynamic_conditional_correlation", lambda: run_dynamic_conditional_correlation(market, cutoff_time=cutoff, canonical=output))
        execute("generalized_autoregressive_score", lambda: run_gas(settled, output, cutoff_time=cutoff))
        execute("hidden_semi_markov_duration", lambda: run_hsmm(history, output, cutoff_time=cutoff, bootstrap_service=bootstrap_service))
        execute("midas_multi_frequency", lambda: run_midas(h1, m1, cutoff_time=cutoff))
        previous_fdr = (((previous.get("quant_research_v7") or {}).get("methods") or {}).get("bds_residual_test") or {}).get("output_metrics", {}).get("online_fdr_state", {}) if isinstance(previous, Mapping) else {}
        execute("bds_residual_test", lambda: run_bds(settled, generation_id=identity["source_generation_id"], cutoff_time=cutoff, bootstrap_service=bootstrap_service, previous_fdr=previous_fdr))
        horizon = int(state.get("quant_v7_user_horizon_hours", state.get("user_exit_horizon_hours", 3)) or 3)
        execute("dynamic_trading_costs", lambda: run_dynamic_trading(output, cutoff_time=cutoff, horizon_hours=horizon))
        execute("coherent_risk", lambda: run_coherent_risk(output, methods.get("dynamic_conditional_correlation"), methods.get("generalized_autoregressive_score"), methods.get("hidden_semi_markov_duration"), cutoff_time=cutoff))
        available = sum(method.get("status") not in {"UNAVAILABLE", "INSUFFICIENT_EVIDENCE", "FAILED_SAFELY"} for method in methods.values())
        overall = "SHADOW_READY" if available >= 7 else "LIMITED_EVIDENCE" if available >= 3 else "INSUFFICIENT_EVIDENCE"
        summary = {"overall_status": overall, "available_method_count": int(available), "method_count": METHOD_COUNT, "sample_count": int(len(h1)), "shadow_only": True, "production_influence_enabled": False}
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        result = {"version": VERSION, "identity": identity, "summary": summary, "methods": methods, "assumptions": ["completed canonical H1 authority", "settled outcomes only where required", "bounded deterministic computation"], "limitations": ["shadow evidence cannot guarantee profit", "unavailable markets/timeframes are never invented"], "performance": {"wall_time_ms": round((time.perf_counter() - started) * 1000.0, 3), "peak_traced_memory_mb": round(peak / 1048576.0, 3), "input_rows": {"h1": len(h1), "m1": len(m1), "settled": len(settled), "metric_history": len(history), "market_history": len(market)}, "method_runtimes_ms": method_runtimes}, "shadow_only": True, "production_influence_enabled": False}
        result["performance"]["serialized_result_bytes"] = len(_json(result).encode("utf-8"))
        output["quant_research_v7"] = result
        output["quant_research_v7_ai_evidence"] = {"identity": identity, "summary": summary, "facts": {"stable_feature_count": _method_metrics(result, "stability_selection").get("stable_feature_count"), "dcc_state": _method_metrics(result, "dynamic_conditional_correlation").get("cross_market_conflict_state"), "gas_state": _method_metrics(result, "generalized_autoregressive_score").get("tail_warning_state"), "hsmm_h1": (_method_metrics(result, "hidden_semi_markov_duration").get("survival_probability") or {}).get("H+1"), "hsmm_h6": (_method_metrics(result, "hidden_semi_markov_duration").get("survival_probability") or {}).get("H+6"), "bds_status": methods["bds_residual_test"].get("status"), "trading_advisory": _method_metrics(result, "dynamic_trading_costs").get("advisory_label"), "coherent_risk": _method_metrics(result, "coherent_risk").get("final_shadow_risk_state")}, "shadow_only": True, "production_influence_enabled": False}
        output.setdefault("metadata", {})["quant_research_v7_status"] = overall
        bundle = build_bundle(result, errors)
        state["quant_research_v7_compact_20260622"] = output["quant_research_v7_ai_evidence"]
        del h1, m1, settled, history
        gc.collect()
        return output, {BUNDLE_KEY: bundle}, {"status": overall, "generation_id": identity["source_generation_id"], "available_method_count": available, "errors": errors, "performance": result["performance"]}
    except Exception as exc:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        previous_v7 = previous.get("quant_research_v7") if isinstance(previous, Mapping) else None
        if isinstance(previous_v7, Mapping) and previous_v7.get("summary", {}).get("overall_status") not in {None, "FAILED_SAFELY"}:
            output["quant_research_v7"] = deepcopy(dict(previous_v7))
            output.setdefault("metadata", {})["quant_research_v7_status"] = "FAILED_SAFELY_PREVIOUS_PRESERVED"
            output["metadata"]["quant_research_v7_error"] = f"{type(exc).__name__}: {exc}"[:500]
        else:
            identity = canonical_identity(output, {})
            output["quant_research_v7"] = {"version": VERSION, "identity": identity, "summary": {"overall_status": "FAILED_SAFELY", "available_method_count": 0, "method_count": METHOD_COUNT, "sample_count": 0, "shadow_only": True, "production_influence_enabled": False}, "methods": {}, "assumptions": [], "limitations": [str(exc)[:300]], "performance": {}, "shadow_only": True, "production_influence_enabled": False}
        gc.collect()
        return output, {BUNDLE_KEY: {table: [] for table in TABLES}}, {"status": "FAILED_SAFELY", "ok": False, "previous_valid_preserved": isinstance(previous_v7, Mapping), "message": str(exc)[:500]}


def query_v7_history(table: str, *, search: str = "", limit: int = 240, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    if table not in TABLES:
        raise ValueError("unsupported V7 table")
    conn = sqlite3.connect(str(db_path)); ensure_schema(conn)
    try:
        sql = f'SELECT * FROM "{table}"'; params: list[Any] = []
        if search:
            sql += " WHERE upper(CAST(payload_json AS TEXT)) LIKE ?"; params.append(f"%{search.upper()}%")
        order = "event_time_utc" if table != "quant_research_v7_error_history" else "event_time_utc"
        sql += f" ORDER BY {order} DESC LIMIT ?"; params.append(max(1, min(int(limit), 2000)))
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


__all__ = ["BUNDLE_KEY", "TABLES", "ensure_schema", "insert_quant_v7_bundle", "build_quant_research_v7_transaction", "query_v7_history"]
