"""Offline regression checks for the July 22 selector/mobile repair.

This script does not call market APIs and does not require Streamlit. Run:
    python tools/validate_selector_sequential_fix_20260722.py
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if importlib.util.find_spec("requests") is None:
    sys.modules["requests"] = SimpleNamespace(Session=type("OfflineSession", (), {}))
if importlib.util.find_spec("statsmodels") is None:
    statsmodels = type(sys)("statsmodels")
    tsa = type(sys)("statsmodels.tsa")
    regime_switching = type(sys)("statsmodels.tsa.regime_switching")
    markov_regression = type(sys)("statsmodels.tsa.regime_switching.markov_regression")
    api = type(sys)("statsmodels.tsa.api")
    markov_regression.MarkovRegression = type("OfflineMarkovRegression", (), {})
    api.VAR = type("OfflineVAR", (), {})
    sys.modules.update({
        "statsmodels": statsmodels,
        "statsmodels.tsa": tsa,
        "statsmodels.tsa.regime_switching": regime_switching,
        "statsmodels.tsa.regime_switching.markov_regression": markov_regression,
        "statsmodels.tsa.api": api,
    })


def validate_presets() -> None:
    from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS, FIRST_TARGET_10, SECOND_TARGET_10
    from core.multi_symbol_load_manager_20260707 import MAX_CANONICAL_SYMBOLS, canonical_universe_from_groups
    assert len(TARGET_FX_SYMBOLS) == 20
    assert len(FIRST_TARGET_10) == 10 and len(SECOND_TARGET_10) == 10
    assert not set(FIRST_TARGET_10) & set(SECOND_TARGET_10)
    assert "XAUUSD" not in TARGET_FX_SYMBOLS
    assert MAX_CANONICAL_SYMBOLS == 20
    canonical = canonical_universe_from_groups({
        "FIRST": list(FIRST_TARGET_10) + ["XAUUSD"],
        "SECOND": list(SECOND_TARGET_10),
        "THIRD": ["BTCUSD"],
    })
    assert canonical == list(TARGET_FX_SYMBOLS)


def validate_subset_orchestration() -> None:
    import core.calculation.run_orchestrator as ro
    import core.field3_three_regime_engine as f3
    import core.global_symbol_context as gsc

    calls: dict[str, object] = {}
    ro.migrate_deployment_schema = lambda *args, **kwargs: None
    ro.save_runtime_preferences = lambda db, symbols, tf: calls.update(saved=list(symbols), saved_tf=tf)

    class FakeScheduler:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *, symbols, timeframe, state, active_symbol, bars, run_id, force_live, progress_callback):
            calls["scheduler_symbols"] = list(symbols)
            calls["active_symbol"] = active_symbol
            frame = pd.DataFrame({
                "open_time": pd.date_range("2026-01-01", periods=30, freq="4h", tz="UTC"),
                "open": [1.0] * 30,
                "high": [2.0] * 30,
                "low": [0.5] * 30,
                "close": [1.5] * 30,
                "volume": [10] * 30,
            })
            return {
                "results": {
                    symbol: {
                        "ok": True,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "frame": frame,
                        "provider": "TWELVE_DATA_KEY_POOL",
                    }
                    for symbol in symbols
                }
            }

    ro.MultiSymbolScheduler = FakeScheduler
    context = SimpleNamespace(
        universe_id="U-TEST",
        configured_symbols=("AUDCAD", "EURUSD", "USDJPY"),
        timeframe="H4",
    )
    gsc.get_global_symbol_context = lambda *args, **kwargs: context
    gsc.mark_universe_loading = lambda *args, **kwargs: context
    gsc.publish_loaded_universe = lambda *args, **kwargs: SimpleNamespace(
        universe_id="U-TEST",
        generation=1,
        configured_symbols=context.configured_symbols,
        loaded_symbols=context.configured_symbols,
        failed_symbols={},
        timeframe="H4",
        latest_completed_candle="2026-01-05T20:00:00+00:00",
    )
    f3.standardize_candles = lambda value: value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()
    f3.candle_hash = lambda frame: "test-hash"

    report = ro.prepare_market_data_for_run(
        {"connector_bars": 30},
        run_id="SEQUENTIAL-SELECTOR-TEST",
        selected_symbols=["USDJPY"],
        timeframe="H4",
        bars=30,
    )
    assert calls["scheduler_symbols"] == ["USDJPY"]
    assert calls["saved"] == ["AUDCAD", "EURUSD", "USDJPY"]
    assert report["requested_symbols"] == ["USDJPY"]
    assert report["request_scope"] == "SUBSET"

    try:
        ro.prepare_market_data_for_run(
            {}, run_id="UNKNOWN-SYMBOL-TEST", selected_symbols=["NOTCONFIGURED"], timeframe="H4", bars=30
        )
    except RuntimeError as exc:
        assert "REQUESTED_SYMBOLS_NOT_IN_GLOBAL_CONFIGURED_UNIVERSE" in str(exc)
    else:
        raise AssertionError("Unknown symbols must remain blocked.")


def validate_table_renderer() -> None:
    from ui.field3_table_renderer_20260918 import render_field3_table
    assert callable(render_field3_table)


def validate_super_quick_fixed20_and_cache() -> None:
    import core.field3_three_regime_engine as field3_engine
    import core.super_quick_field3_20260722 as fast
    from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS

    symbols = list(TARGET_FX_SYMBOLS)
    frames = {}
    for offset, symbol in enumerate(symbols):
        close = pd.Series([1.0 + offset * 0.01 + row * 0.0001 for row in range(180)])
        frames[symbol] = pd.DataFrame({
            "open_time": pd.date_range("2026-01-01", periods=180, freq="h", tz="UTC"),
            "open": close - 0.00005,
            "high": close + 0.00015,
            "low": close - 0.00015,
            "close": close,
            "volume": [100 + row for row in range(180)],
        })
    state = {
        "market_data_run_results_20260705": {
            "results": {
                symbol: {"ok": True, "symbol": symbol, "timeframe": "H1", "frame": frame}
                for symbol, frame in frames.items()
            } | {"XAUUSD": {"ok": True, "symbol": "XAUUSD", "timeframe": "H1", "frame": next(iter(frames.values()))}}
        }
    }
    context = SimpleNamespace(
        universe_id="U-FIXED20", generation=1, timeframe="H1", loaded_symbols=tuple(symbols + ["XAUUSD"]),
    )
    fast.get_global_symbol_context = lambda *args, **kwargs: context
    fast.publish_completed_generation = lambda *args, **kwargs: SimpleNamespace(publication_status="PUBLISHED", generation=1)
    original_persist = field3_engine.persist_field3_v2
    field3_engine.persist_field3_v2 = lambda *args, **kwargs: {"rows": 20}
    try:
        first = fast.run_super_quick_field3(state, symbols=symbols + ["XAUUSD"], timeframe="H1")
        second = fast.run_super_quick_field3(state, symbols=symbols + ["XAUUSD"], timeframe="H1")
    finally:
        field3_engine.persist_field3_v2 = original_persist
    assert first["completed_symbols"] == 20
    assert first["selected_symbols"] == symbols
    assert first["provider_requests"] == 0
    assert not first["reused_cached_calculation"]
    assert second["completed_symbols"] == 20
    assert second["reused_cached_calculation"]


def main() -> None:
    validate_presets()
    validate_subset_orchestration()
    validate_table_renderer()
    validate_super_quick_fixed20_and_cache()
    print("ALL_FIXED20_FIELD3_TESTS_PASS")


if __name__ == "__main__":
    main()
