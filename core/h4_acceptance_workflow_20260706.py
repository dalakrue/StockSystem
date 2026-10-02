"""Deterministic offline ten-symbol H4 acceptance workflow.

This is an integration fixture, not a market-performance claim.  It exercises
exact-symbol publication, SQLite reload, Field 1/2 switching and identity
separation without network access or API credentials.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sqlite3

import numpy as np
import pandas as pd

from core.child_snapshot_publication_20260706 import (
    latest_publication,
    mark_reload_validation,
    publish_complete_child,
    validate_child_state,
)
from core.multi_symbol_field10_20260701 import TOP_10_CURRENCY_PAIRS
from core.powerbi_child_bundle_20260706 import build_and_store_powerbi_bundle
from core.runtime_state_cache_20260628 import save_runtime_state
from core.serialization_compat_20260702 import loads as serializer_loads
from core.timeframe_identity_migration_20260706 import migrate_timeframe_identity

VERSION = "offline-h4-acceptance-20260706-v1"


def _ohlc(symbol_index: int, *, rows: int = 160) -> pd.DataFrame:
    end = pd.Timestamp("2026-07-03T20:00:00Z")
    times = pd.date_range(end=end, periods=rows, freq="4h", tz="UTC")
    base = 1.02 + symbol_index * 0.071
    step = np.arange(rows, dtype=float)
    close = base + step * (0.00005 + symbol_index * 0.000001) + np.sin(step / 8.0) * 0.0004
    open_ = close - 0.00008
    return pd.DataFrame({
        "time": times,
        "open": open_,
        "high": np.maximum(open_, close) + 0.00025,
        "low": np.minimum(open_, close) - 0.00025,
        "close": close,
        "volume": 1000.0 + step + symbol_index * 100.0,
    })


def _canonical(symbol: str, index: int, frame: pd.DataFrame, parent: str, child: str) -> dict[str, Any]:
    completed = pd.Timestamp(frame["time"].iloc[-1]).isoformat()
    created = pd.Timestamp("2026-07-03T20:01:00Z").isoformat()
    expires = pd.Timestamp("2026-07-10T20:01:00Z").isoformat()
    return {
        "run_id": f"CANON-{symbol}-H4-001",
        "canonical_calculation_id": f"CANON-{symbol}-H4-001",
        "calculation_generation": index + 1,
        "generation_id": f"GEN-{symbol}-H4-001",
        "data_signature": f"SIG-{symbol}-H4-001",
        "snapshot_hash": f"HASH-{symbol}-H4-001",
        "source_id": f"OFFLINE-FIXTURE-{symbol}",
        "symbol": symbol,
        "timeframe": "H4",
        "source": "DETERMINISTIC_OFFLINE_FIXTURE",
        "latest_completed_candle_time": completed,
        "completed_broker_candle": completed,
        "created_at": created,
        "expires_at": expires,
        "schema_version": "acceptance-v1",
        "calculation_version": "protected-current-fixture",
        "calculation_status": "COMPLETED",
        "market": {"latest_completed_candle_time": completed},
        "final_decision": {"decision": "WAIT", "less_risky_decision": "WAIT"},
        "parent_run_id": parent,
        "child_run_id": child,
    }


def _state(symbol: str, index: int, frame: pd.DataFrame, parent: str, selected: list[str]) -> dict[str, Any]:
    child = f"{parent}:{symbol}"
    canonical = _canonical(symbol, index, frame, parent, child)
    completed = canonical["completed_broker_candle"]
    history = frame.tail(40).copy()
    history.insert(1, "Decision", "WAIT")
    history["Symbol"] = symbol
    rank = pd.DataFrame([{
        "Time": completed,
        "Completed Broker Candle": completed,
        "Timeframe": "H4",
        "Rank": index + 1,
        "Symbol": symbol,
        "Less-Risky Bias": "WAIT",
        "Stable Daily Bias": "WAIT",
        "Higher Standard Regime": "RANGE",
        "Expected Value / Return": 0.0001 + index * 0.00001,
        "Probability": 50.0 + index,
        "Reliability": 70.0 + index,
        "Transition Risk": 20.0 + index,
        "Risk": "MODERATE",
        "Data Quality": "A",
        "Available Candles": len(frame),
        "Required Candles": 150,
        "Source ID": canonical["source_id"],
        "Snapshot Hash": canonical["snapshot_hash"],
        "Calculation Status": "COMPLETED",
    }])
    return {
        "canonical_decision_result_20260617": canonical,
        "last_valid_canonical_decision_result_20260617": canonical,
        "successful_calculation_generation_20260617": index + 1,
        "canonical_completed_ohlc_df_20260617": frame.copy(),
        "last_df": frame.copy(),
        "field1_table1_decision_history_20260628": history,
        "full_metric_history_df_20260618": history.copy(),
        "regime_standard_detail_tables_published_20260618": {
            "lower": pd.DataFrame([{"Symbol": symbol, "Regime": "RANGE", "Timeframe": "H4"}]),
            "middle": pd.DataFrame([{"Symbol": symbol, "Regime": "RANGE", "Timeframe": "H4"}]),
            "higher": pd.DataFrame([{"Symbol": symbol, "Regime": "RANGE", "Timeframe": "H4"}]),
        },
        "field3_regime_lifecycle_monitor_20260701": {"symbol": symbol, "status": "AVAILABLE"},
        "field10_multi_symbol_summary_20260701": rank,
        "field10_daily_higher_regime_20260701": rank.copy(),
        "field10_hourly_quality_20260701": rank.copy(),
        "timeframe": "H4",
        "selected_timeframe": "H4",
        "symbol": symbol,
        "source": "DETERMINISTIC_OFFLINE_FIXTURE",
        "settings_main_symbol": selected[0],
        "multi_symbol_main_symbol_20260702": selected[0],
        "connector_symbol": selected[0],
        "connector_symbol_20260702": selected[0],
        "calculation_symbol": symbol,
        "calculation_symbol_20260702": symbol,
        "multi_symbol_selected_20260701": list(selected),
        "multi_symbol_parent_run_id_20260701": parent,
        "multi_symbol_current_child_id_20260701": child,
        "multi_symbol_child_run_active_20260701": {
            "parent_run_id": parent, "child_run_id": child, "symbol": symbol,
        },
        "active_page": "Lunch",
        "active_lunch_field": "Field 10",
        "lunch_active_field_selector_20260624": "10. Open / Close — Multi-Symbol Rank, Data Quality and Higher-Regime Monitor",
        "lunch_display_symbol_20260702": symbol,
        "active_snapshot_symbol_20260702": symbol,
        "multi_symbol_active_20260701": symbol,
    }


def _read_cache(path: Path) -> dict[str, Any]:
    import gzip
    payload = serializer_loads(gzip.decompress(path.read_bytes()))
    return dict(payload) if isinstance(payload, dict) else {}


def run_offline_h4_acceptance(workdir: Path | str) -> dict[str, Any]:
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    cache_dir = root / "multi_symbol_runtime"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = root / "acceptance.sqlite3"
    migration = migrate_timeframe_identity(db_path, create_backup=True)
    selected = list(TOP_10_CURRENCY_PAIRS)
    parent = "MS-OFFLINE-H4-ACCEPTANCE-001"
    publications: dict[str, Any] = {}
    states: dict[str, dict[str, Any]] = {}

    for index, symbol in enumerate(selected):
        frame = _ohlc(index)
        state = _state(symbol, index, frame, parent, selected)
        powerbi = build_and_store_powerbi_bundle(state, allow_causal_fallback=True)
        cache_path = cache_dir / f"{symbol}.pkl.gz"
        cache = save_runtime_state(state, status={"ok": True, "status": "COMPLETED"}, scope="LUNCH_CORE", path=cache_path)
        publication = publish_complete_child(state, runtime_snapshot_path=cache_path, db_path=db_path)
        reloaded = _read_cache(cache_path).get("state") or {}
        reload_validation = validate_child_state(reloaded, runtime_snapshot_path=cache_path)
        identity = publication.get("validation", {}).get("identity", {})
        if identity:
            mark_reload_validation(
                publication=identity, db_path=db_path,
                passed=bool(reload_validation.get("ok")), detail=reload_validation,
            )
        completed = latest_publication(symbol=symbol, timeframe="H4", db_path=db_path, completed_only=True)
        states[symbol] = state
        publications[symbol] = {
            "powerbi": powerbi,
            "cache": cache,
            "initial_publication": publication,
            "reload_validation": reload_validation,
            "completed_publication": completed,
            "close_tail": float(frame["close"].iloc[-1]),
        }

    # Exercise the same read-only Lunch restore used by Field 1 and Field 2.
    from core import multi_symbol_field10_20260701 as multi
    old_db, old_cache = multi.DB_PATH, multi.CACHE_DIR
    multi.DB_PATH, multi.CACHE_DIR = db_path, cache_dir
    try:
        display_state: dict[str, Any] = {
            "timeframe": "H4", "selected_timeframe": "H4",
            "settings_main_symbol": selected[0],
            "multi_symbol_main_symbol_20260702": selected[0],
            "connector_symbol": selected[0],
            "connector_symbol_20260702": selected[0],
            "multi_symbol_selected_20260701": list(selected),
        }
        field1_load = multi.activate_symbol_view(display_state, selected[1])
        field1_symbol = str((display_state.get("canonical_decision_result_20260617") or {}).get("symbol") or "")
        _field1_history = display_state.get("field1_table1_decision_history_20260628")
        field1_rows = len(_field1_history) if isinstance(_field1_history, pd.DataFrame) else 0
        settings_after_field1 = display_state.get("settings_main_symbol")
        field2_load = multi.activate_symbol_view(display_state, selected[2])
        field2_bundle = dict(display_state.get("powerbi_child_bundle_20260706") or {})
        settings_after_field2 = display_state.get("settings_main_symbol")
        authorities = {
            key: display_state.get(key) for key in (
                "lunch_display_symbol_20260702", "canonical_display_symbol_20260705",
                "multi_symbol_active_20260701", "field1_display_symbol_20260706",
                "field2_display_symbol_20260706", "field3_display_symbol_20260706",
                "field10_display_symbol_20260706", "field11_display_symbol_20260706",
            )
        }
        # Simulate browser/session clear: create a fresh state and restore again.
        cleared_state: dict[str, Any] = {
            "timeframe": "H4", "selected_timeframe": "H4",
            "settings_main_symbol": selected[0], "multi_symbol_main_symbol_20260702": selected[0],
            "multi_symbol_selected_20260701": list(selected),
        }
        reload_after_clear = {
            symbol: multi.activate_symbol_view(cleared_state, symbol).get("status") for symbol in selected
        }
    finally:
        multi.DB_PATH, multi.CACHE_DIR = old_db, old_cache

    completed_symbols = [s for s, item in publications.items() if item["completed_publication"]]
    distinct_hashes = {item["completed_publication"].get("snapshot_hash") for item in publications.values() if item["completed_publication"]}
    distinct_sources = {item["completed_publication"].get("source_id") for item in publications.values() if item["completed_publication"]}
    all_reload = all(item["reload_validation"].get("ok") for item in publications.values())
    all_fallback_labelled = all(
        item["powerbi"].get("ok") and item["powerbi"].get("bundle", {}).get("calibration_status") == "NOT_CALIBRATED"
        for item in publications.values()
    )
    authorities_agree = len(set(authorities.values())) == 1 and next(iter(set(authorities.values())), "") == selected[2]
    cleared_reload_ok = all(value == "COMPLETE_CHILD_RESTORED" for value in reload_after_clear.values())
    checks = {
        "ten_symbols_completed": len(completed_symbols) == 10,
        "h4_required_150": all(item["reload_validation"].get("required_candles") == 150 for item in publications.values()),
        "all_reload_valid": all_reload,
        "distinct_child_snapshot_hashes": len(distinct_hashes) == 10,
        "distinct_exact_symbol_sources": len(distinct_sources) == 10,
        "field1_load_changed_identity": field1_load.get("status") == "COMPLETE_CHILD_RESTORED" and field1_symbol == selected[1] and field1_rows > 1,
        "field2_load_changed_bundle": field2_load.get("status") == "COMPLETE_CHILD_RESTORED" and field2_bundle.get("symbol") == selected[2],
        "settings_main_symbol_unchanged": settings_after_field1 == selected[0] and settings_after_field2 == selected[0],
        "display_authorities_agree": authorities_agree,
        "fallback_truthfully_labelled": all_fallback_labelled,
        "session_clear_sqlite_reload": cleared_reload_ok,
    }
    with sqlite3.connect(str(db_path)) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        child_count = conn.execute("SELECT COUNT(*) FROM child_snapshot_publication_20260706 WHERE publication_status='COMPLETED'").fetchone()[0]
        powerbi_count = conn.execute("SELECT COUNT(*) FROM field2_powerbi_publication_20260706").fetchone()[0]
    checks["sqlite_integrity"] = integrity == "ok"
    checks["sqlite_has_ten_children"] = child_count == 10
    checks["sqlite_has_ten_powerbi_bundles"] = powerbi_count == 10
    ok = all(checks.values())
    result = {
        "ok": ok,
        "status": "PASSED" if ok else "FAILED",
        "version": VERSION,
        "mode": "DETERMINISTIC_OFFLINE_FIXTURE",
        "live_api_credentials_used": False,
        "selected_symbols": selected,
        "timeframe": "H4",
        "completed_symbols": completed_symbols,
        "checks": checks,
        "field1_load": {k: v for k, v in field1_load.items() if k not in {"publication", "validation"}},
        "field2_load": {k: v for k, v in field2_load.items() if k not in {"publication", "validation"}},
        "field2_loaded_symbol": field2_bundle.get("symbol"),
        "display_authorities": authorities,
        "reload_after_session_clear": reload_after_clear,
        "database": {"path": str(db_path), "integrity": integrity, "completed_children": child_count, "powerbi_bundles": powerbi_count},
        "migration": migration,
        "real_data_availability": {
            "status": "NOT_EVALUATED_IN_OFFLINE_TEST",
            "reason": "No live API credentials were used; deterministic real-structure OHLC fixtures validate plumbing only.",
        },
    }
    report_path = root / "h4_acceptance_result.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    result["report_path"] = str(report_path)
    return result


__all__ = ["VERSION", "run_offline_h4_acceptance"]
