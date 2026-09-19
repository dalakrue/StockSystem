"""Atomic persistence and canonical transaction builder for Quant Research V3."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import math
import sqlite3
import time

import pandas as pd

from core.quant_research_v3_contract_20260622 import (
    HORIZONS, METHOD_VERSION, ResearchIdentity, identity_from_canonical, json_safe,
    normalize_completed_h1, stable_hash, utc_now_iso,
)
from services.canonical_snapshot_store import DB_PATH

VERSION = "quant-research-v3-store-20260622-v1"
BUNDLE_KEY = "__quant_research_v3_20260622__"

COMMON_COLUMNS = """
  record_key TEXT PRIMARY KEY,
  run_id TEXT, canonical_calculation_id TEXT, source_generation_id TEXT NOT NULL,
  symbol TEXT, timeframe TEXT, broker_timezone TEXT, completed_h1_time TEXT,
  calculation_created_at TEXT, source_data_signature TEXT,
  method_name TEXT, method_version TEXT, horizon_hours INTEGER,
  condition_key TEXT, sample_count INTEGER, minimum_sample_required INTEGER,
  fallback_level TEXT, reliability_status TEXT, assumption_status TEXT,
  shadow_only INTEGER NOT NULL DEFAULT 1,
  production_influence_enabled INTEGER NOT NULL DEFAULT 0,
  calculation_error TEXT, exact_limitations_json TEXT,
  settled_target_time TEXT, status TEXT, value_numeric REAL, value_text TEXT,
  evaluated_at TEXT NOT NULL, payload_json TEXT NOT NULL
"""

TABLES = (
    "quant_research_v3_run",
    "yz_volatility_history",
    "har_volatility_forecast_history",
    "bipower_jump_proxy_history",
    "caviar_quantile_history",
    "joint_var_es_score_history",
    "semiparametric_var_es_history",
    "cvar_risk_budget_history",
    "density_pit_history",
    "berkowitz_density_test_history",
    "execution_cost_shadow_history",
    "quant_research_v3_error_history",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    for table in TABLES:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}"({COMMON_COLUMNS})')
    for table in TABLES:
        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_completed" ON "{table}"(completed_h1_time DESC)')
        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_generation" ON "{table}"(source_generation_id)')
        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_horizon" ON "{table}"(horizon_hours)')
        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_reliability" ON "{table}"(reliability_status)')
        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_condition" ON "{table}"(condition_key)')
        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table}_settled" ON "{table}"(settled_target_time)')


def _normalise_row(table: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(json_safe(raw))
    payload = dict(row)
    row.setdefault("evaluated_at", row.get("calculation_created_at") or utc_now_iso())
    row.setdefault("status", row.get("reliability_status") or "UNKNOWN")
    row.setdefault("shadow_only", True)
    row.setdefault("production_influence_enabled", False)
    row["shadow_only"] = 1 if bool(row.get("shadow_only")) else 0
    row["production_influence_enabled"] = 1 if bool(row.get("production_influence_enabled")) else 0
    limitations = row.get("exact_limitations") or row.get("exact_limitations_json") or []
    row["exact_limitations_json"] = json.dumps(json_safe(limitations), ensure_ascii=False, separators=(",", ":"))
    row["payload_json"] = json.dumps(json_safe(payload), ensure_ascii=False, separators=(",", ":"))
    row.setdefault("record_key", stable_hash([
        table, row.get("source_generation_id"), row.get("method_version"), row.get("horizon_hours"),
        row.get("condition_key"), row.get("settled_target_time"), row.get("method_name"),
    ]))
    return row


def insert_quant_v3_bundle(conn: sqlite3.Connection, bundle: Mapping[str, Iterable[Mapping[str, Any]]]) -> dict[str, Any]:
    """Insert all Quant V3 rows inside the caller's existing transaction."""
    ensure_schema(conn)
    result: dict[str, Any] = {}
    for table, rows in bundle.items():
        if table not in TABLES:
            continue
        columns = {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
        inserted = ignored = 0
        for raw in rows or []:
            row = _normalise_row(table, raw)
            selected = [name for name in row if name in columns]
            if not selected:
                continue
            sql = f'INSERT OR IGNORE INTO "{table}"({",".join(chr(34)+x+chr(34) for x in selected)}) VALUES({",".join("?" for _ in selected)})'
            before = conn.total_changes
            conn.execute(sql, [row[name] for name in selected])
            if conn.total_changes > before:
                inserted += 1
            else:
                ignored += 1
        result[table] = {"inserted": inserted, "idempotent_ignored": ignored}
    return result


def _base_row(contract: Mapping[str, Any], *, horizon: int | None = None, condition: str | None = None) -> dict[str, Any]:
    keys = (
        "run_id", "canonical_calculation_id", "source_generation_id", "symbol", "timeframe",
        "broker_timezone", "completed_h1_time", "calculation_created_at", "source_data_signature",
        "method_name", "method_version", "sample_count", "minimum_sample_required", "fallback_level",
        "reliability_status", "assumption_status", "shadow_only", "production_influence_enabled",
        "calculation_error", "exact_limitations", "status",
    )
    row = {key: contract.get(key) for key in keys}
    row["horizon_hours"] = int(horizon if horizon is not None else contract.get("horizon_hours") or 1)
    row["condition_key"] = str(condition if condition is not None else contract.get("condition_key") or "GLOBAL")
    return row


def build_persistence_bundle(result: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    identity = result.get("identity") or {}
    summary = result.get("summary") or {}
    bundle: dict[str, list[dict[str, Any]]] = {table: [] for table in TABLES}
    run_contract = {
        **identity,
        "method_name": "QUANT_RESEARCH_V3_RUN",
        "method_version": VERSION,
        "sample_count": result.get("input_contract", {}).get("retained_row_count", 0),
        "minimum_sample_required": 24,
        "fallback_level": "COMPOSITE",
        "reliability_status": summary.get("overall_quant_v3_status"),
        "assumption_status": "METHOD_SPECIFIC",
        "shadow_only": True,
        "production_influence_enabled": False,
        "status": summary.get("overall_quant_v3_status"),
        "exact_limitations": result.get("limitations") or [],
    }
    run_row = _base_row(run_contract)
    run_row.update({"value_text": summary.get("overall_quant_v3_status"), "payload": result.get("run_audit") or {}})
    bundle["quant_research_v3_run"].append(run_row)

    vol = result.get("volatility") or {}
    yz = vol.get("yang_zhang") or {}
    row = _base_row(yz)
    row.update({"value_numeric": yz.get("yang_zhang_volatility"), "value_text": yz.get("status")})
    bundle["yz_volatility_history"].append({**row, **yz})
    har = vol.get("har_style") or {}
    for horizon, data in (har.get("horizons") or {}).items():
        row = _base_row(har, horizon=int(horizon), condition="GLOBAL")
        row.update({"value_numeric": data.get("forecast_volatility"), "value_text": data.get("status"), "horizon_output": data})
        bundle["har_volatility_forecast_history"].append(row)
    jump = vol.get("jump_proxy") or {}
    row = _base_row(jump)
    row.update({"value_numeric": jump.get("jump_share"), "value_text": "JUMP" if jump.get("latest_move_is_jump") else jump.get("status")})
    bundle["bipower_jump_proxy_history"].append({**row, **jump})

    tail = result.get("tail_density") or {}
    caviar = tail.get("caviar") or {}
    for horizon, hdata in (caviar.get("horizons") or {}).items():
        for level, qdata in (hdata.get("quantiles") or {}).items():
            row = _base_row(caviar, horizon=int(horizon), condition=f"Q{level}")
            row.update({"value_numeric": qdata.get("quantile_forecast"), "value_text": qdata.get("selected_specification"), "quantile_level": level, "quantile_output": qdata})
            bundle["caviar_quantile_history"].append(row)
    joint = tail.get("joint_var_es") or {}
    for horizon, levels in (joint.get("rankings") or {}).items():
        for alpha, data in (levels or {}).items():
            row = _base_row(joint, horizon=int(horizon), condition=f"ALPHA_{alpha}")
            row.update({"value_text": data.get("winner"), "score_output": data})
            bundle["joint_var_es_score_history"].append(row)
    taylor = tail.get("taylor_var_es") or {}
    for horizon, hdata in (taylor.get("horizons") or {}).items():
        for alpha, data in (hdata.get("levels") or {}).items():
            row = _base_row(taylor, horizon=int(horizon), condition=f"ALPHA_{alpha}")
            row.update({"value_numeric": data.get("var"), "value_text": data.get("status"), "var_es_output": data})
            bundle["semiparametric_var_es_history"].append(row)
    cvar = tail.get("cvar_risk_budget") or {}
    row = _base_row(cvar, horizon=int(cvar.get("horizon_hours") or 1), condition=str(cvar.get("condition_key") or "GLOBAL"))
    row.update({"value_numeric": cvar.get("selected_risk_multiplier"), "value_text": cvar.get("status")})
    bundle["cvar_risk_budget_history"].append({**row, **cvar})
    pit = tail.get("density_pit") or {}
    for horizon, hdata in (pit.get("horizons") or {}).items():
        records = hdata.get("records_tail") or []
        if records:
            for item in records:
                row = _base_row(pit, horizon=int(horizon), condition="GLOBAL")
                row.update({"settled_target_time": item.get("settled_target_time"), "value_numeric": item.get("pit_value"), "value_text": item.get("cdf_construction_status"), "pit_output": item})
                bundle["density_pit_history"].append(row)
        else:
            row = _base_row(pit, horizon=int(horizon), condition="GLOBAL")
            row.update({"value_numeric": hdata.get("pit_mean"), "value_text": hdata.get("status"), "pit_summary": hdata})
            bundle["density_pit_history"].append(row)
    berk = tail.get("berkowitz") or {}
    for horizon, data in (berk.get("horizons") or {}).items():
        row = _base_row(berk, horizon=int(horizon), condition="GLOBAL")
        row.update({"value_numeric": data.get("lr_statistic"), "value_text": data.get("status"), "test_output": data})
        bundle["berkowitz_density_test_history"].append(row)
    execution = result.get("execution") or {}
    row = _base_row(execution, horizon=int(execution.get("horizon_hours") or 1), condition="GLOBAL")
    row.update({"value_numeric": execution.get("total_expected_execution_cost"), "value_text": execution.get("status")})
    bundle["execution_cost_shadow_history"].append({**row, **execution})

    contracts = [yz, har, jump, caviar, joint, taylor, cvar, pit, berk, execution]
    for contract in contracts:
        if contract.get("calculation_error") or contract.get("status") == "UNAVAILABLE":
            row = _base_row(contract)
            row.update({"value_text": contract.get("calculation_error") or contract.get("status"), "error_payload": contract})
            bundle["quant_research_v3_error_history"].append(row)
    return bundle


def _compact_density(pit: Mapping[str, Any]) -> dict[str, Any]:
    compact = {k: v for k, v in pit.items() if k != "horizons"}
    compact_h: dict[str, Any] = {}
    for horizon, data in (pit.get("horizons") or {}).items():
        compact_h[horizon] = {k: v for k, v in data.items() if k not in {"all_pit_values", "records_tail"}}
        compact_h[horizon]["records_tail"] = list(data.get("records_tail") or [])[-8:]
    compact["horizons"] = compact_h
    return compact


def _first_tail_metric(taylor: Mapping[str, Any], horizon: int, alpha: str, name: str) -> Any:
    return (((taylor.get("horizons") or {}).get(str(horizon)) or {}).get("levels") or {}).get(alpha, {}).get(name)


def _overall_status(result: Mapping[str, Any]) -> str:
    statuses = []
    for contract in (
        (result.get("volatility") or {}).get("yang_zhang") or {},
        (result.get("volatility") or {}).get("har_style") or {},
        (result.get("volatility") or {}).get("jump_proxy") or {},
        (result.get("tail_density") or {}).get("caviar") or {},
        (result.get("tail_density") or {}).get("taylor_var_es") or {},
        (result.get("tail_density") or {}).get("berkowitz") or {},
        result.get("execution") or {},
    ):
        statuses.append(str(contract.get("status") or contract.get("reliability_status") or "UNAVAILABLE").upper())
    if all(x in {"UNAVAILABLE", "INSUFFICIENT_SAMPLE", "UNVERIFIED_COST_MODEL"} for x in statuses):
        return "INSUFFICIENT_EVIDENCE"
    if "FAIL" in statuses:
        return "WARNING"
    if any(x in {"WARNING", "UNAVAILABLE"} for x in statuses):
        return "LIMITED"
    return "SHADOW_READY"


def guard_direction(protected_direction: str, proposed_direction: str | None) -> str:
    """The only permitted directional change is a downgrade to WAIT."""
    protected = str(protected_direction or "WAIT").upper()
    proposed = str(proposed_direction or protected).upper()
    if proposed == protected or proposed == "WAIT":
        return proposed
    return protected


def build_quant_research_v3_transaction(
    canonical: Mapping[str, Any],
    *,
    completed_h1: pd.DataFrame,
    previous: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build one shadow generation and stage all rows for the canonical transaction."""
    started = time.perf_counter()
    canonical_out = dict(canonical or {})
    previous = previous or {}
    try:
        completed_time = canonical_out.get("latest_completed_candle_time")
        frame, frame_meta = normalize_completed_h1(completed_h1, completed_h1_time=completed_time, max_rows=1500)
        identity = identity_from_canonical(canonical_out, frame_meta)
        from core.ohlc_volatility_research_20260622 import build_ohlc_volatility_stack
        from core.tail_density_research_20260622 import build_tail_density_stack
        from core.execution_cost_research_20260622 import execution_cost_advisory
        volatility = build_ohlc_volatility_stack(frame, identity, canonical=canonical_out)
        tail = build_tail_density_stack(frame, identity, volatility_stack=volatility, canonical=canonical_out)
        execution = execution_cost_advisory(identity, canonical_out, volatility)
        result: dict[str, Any] = {
            "version": METHOD_VERSION,
            "identity": identity.as_dict(),
            "input_contract": frame_meta,
            "volatility": volatility,
            "tail_density": tail,
            "execution": execution,
            "production_influence_enabled": False,
            "shadow_only": True,
            "limitations": [
                "All ten methods are delivered in SHADOW mode with production_influence_enabled=False.",
                "No exact theorem guarantee is claimed when H1 resolution, sample size, independence, distribution or market-impact assumptions are unsupported.",
                "The layer can support evidence, warnings, lower trust/risk, or recommend WAIT; it cannot create or reverse BUY/SELL.",
            ],
            "run_audit": {
                "bounded_live_rows": len(frame),
                "calculated_only_inside_settings_transaction": True,
                "complete_h1_only": True,
                "source_data_signature": frame_meta.get("source_data_signature"),
            },
        }
        taylor = tail.get("taylor_var_es") or {}
        har_h1 = (((volatility.get("har_style") or {}).get("horizons") or {}).get("1") or {})
        jump = volatility.get("jump_proxy") or {}
        cvar = tail.get("cvar_risk_budget") or {}
        berk = tail.get("berkowitz") or {}
        summary = {
            "yz_volatility": (volatility.get("yang_zhang") or {}).get("yang_zhang_volatility"),
            "har_volatility_state": har_h1.get("superiority_status") or har_h1.get("status") or (volatility.get("har_style") or {}).get("status"),
            "har_h1_forecast_volatility": har_h1.get("forecast_volatility"),
            "jump_risk": "JUMP" if jump.get("latest_move_is_jump") else ("NO_JUMP" if jump.get("status") == "AVAILABLE" else jump.get("status")),
            "jump_share": jump.get("jump_share"),
            "var_5pct_1h": _first_tail_metric(taylor, 1, "0.05", "var"),
            "expected_shortfall_5pct_1h": _first_tail_metric(taylor, 1, "0.05", "es"),
            "var_5pct_3h": _first_tail_metric(taylor, 3, "0.05", "var"),
            "var_5pct_6h": _first_tail_metric(taylor, 6, "0.05", "var"),
            "cvar_risk_multiplier": cvar.get("selected_risk_multiplier"),
            "density_test": berk.get("status"),
            "execution_cost_status": execution.get("status"),
            "generation_id": identity.source_generation_id,
            "completed_h1_time": identity.completed_h1_time,
            "shadow_only": True,
            "production_influence_enabled": False,
        }
        result["summary"] = summary
        summary["overall_quant_v3_status"] = _overall_status(result)
        unsafe = bool(berk.get("status") == "FAIL" or (jump.get("latest_move_is_jump") and (jump.get("jump_share") or 0) > 0.5) or cvar.get("selected_risk_multiplier") == 0.0)
        protected = str((canonical_out.get("final_decision") or {}).get("final_decision") or "WAIT")
        result["shadow_wait_recommendation"] = "WAIT" if unsafe else protected
        result["protected_direction"] = protected
        result["direction_after_guard"] = guard_direction(protected, result["shadow_wait_recommendation"])
        result["direction_reversal_possible"] = False
        result["runtime_ms"] = round((time.perf_counter() - started) * 1000.0, 3)

        compact = {
            "version": result["version"], "identity": result["identity"], "input_contract": result["input_contract"],
            "summary": summary, "shadow_only": True, "production_influence_enabled": False,
            "protected_direction": protected, "shadow_wait_recommendation": result["shadow_wait_recommendation"],
            "direction_reversal_possible": False, "limitations": result["limitations"],
            "volatility": volatility,
            "tail_density": {**tail, "density_pit": _compact_density(tail.get("density_pit") or {})},
            "execution": {k: v for k, v in execution.items() if k != "schedules"},
            "runtime_ms": result["runtime_ms"],
        }
        canonical_out["quant_research_v3"] = compact
        canonical_out.setdefault("metadata", {})["quant_research_v3_status"] = summary["overall_quant_v3_status"]
        canonical_out["metadata"]["quant_research_v3_production_influence_enabled"] = False
        canonical_out["quant_research_v3_ai_evidence"] = {
            "generation_id": identity.source_generation_id,
            "completed_h1_time": identity.completed_h1_time,
            "sample_count": frame_meta.get("retained_row_count"),
            "summary": summary,
            "fallbacks": {
                "yang_zhang": (volatility.get("yang_zhang") or {}).get("fallback_level"),
                "har": (volatility.get("har_style") or {}).get("fallback_level"),
                "jump": (volatility.get("jump_proxy") or {}).get("fallback_level"),
                "tail": taylor.get("fallback_level"),
                "density": berk.get("fallback_level"),
                "execution": execution.get("fallback_level"),
            },
            "limitations": result["limitations"],
        }
        known = list(canonical_out.get("known_limitations") or [])
        for limitation in result["limitations"]:
            if limitation not in known:
                known.append(limitation)
        canonical_out["known_limitations"] = known[:24]
        bundle = build_persistence_bundle(result)
        return canonical_out, {BUNDLE_KEY: bundle}, {
            "version": VERSION,
            "status": summary["overall_quant_v3_status"],
            "generation_id": identity.source_generation_id,
            "completed_h1_time": identity.completed_h1_time,
            "rows_staged": sum(len(v) for v in bundle.values()),
            "runtime_ms": result["runtime_ms"],
            "production_influence_enabled": False,
            "protected_direction_unchanged": protected == str((canonical_out.get("final_decision") or {}).get("final_decision") or "WAIT"),
        }
    except Exception as exc:
        previous_v3 = previous.get("quant_research_v3") if isinstance(previous.get("quant_research_v3"), Mapping) else None
        if previous_v3:
            canonical_out["quant_research_v3"] = dict(previous_v3)
            canonical_out["quant_research_v3"]["current_generation_error"] = str(exc)[:1000]
            canonical_out["quant_research_v3"]["last_valid_shadow_result_preserved"] = True
        canonical_out.setdefault("metadata", {})["quant_research_v3_status"] = "FAILED_SAFELY"
        canonical_out["metadata"]["quant_research_v3_error"] = str(exc)[:1000]
        return canonical_out, {}, {
            "version": VERSION, "status": "FAILED_SAFELY", "error": str(exc),
            "production_influence_enabled": False, "last_valid_shadow_result_preserved": bool(previous_v3),
        }


def latest_quant_v3_summary(*, db_path: Path | str = DB_PATH) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {}
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=3)
    try:
        row = conn.execute('SELECT payload_json FROM quant_research_v3_run ORDER BY completed_h1_time DESC,evaluated_at DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else {}
    except Exception:
        return {}
    finally:
        conn.close()


__all__ = [
    "VERSION", "BUNDLE_KEY", "TABLES", "ensure_schema", "insert_quant_v3_bundle",
    "build_persistence_bundle", "guard_direction", "build_quant_research_v3_transaction",
    "latest_quant_v3_summary",
]
