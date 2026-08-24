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
    tree = ast.parse((ROOT / "ui" / "multi_symbol_settings_20260701.py").read_text(encoding="utf-8"))
    values: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in {
                "FIRST_BEST_10_CURRENCY_PAIRS",
                "SECOND_BEST_10_CURRENCY_POOL",
                "THIRD_BEST_10_SPREAD_UNDER_25",
            }:
                values[node.target.id] = ast.literal_eval(node.value)
    first = values["FIRST_BEST_10_CURRENCY_PAIRS"]
    second = values["SECOND_BEST_10_CURRENCY_POOL"][:10]
    third = values["THIRD_BEST_10_SPREAD_UNDER_25"]
    assert len(first) == 10 and len(second) == 10 and len(third) == 10
    assert "EURAUD" in first and "EURUSD" not in first
    assert "EURUSD" in second and "EURAUD" not in second
    assert "DXY" in third
    assert not set(first) & set(second)
    assert not set(first + second) & set(third)

    from core.multi_symbol_load_manager_20260707 import MAX_CANONICAL_SYMBOLS, canonical_universe_from_groups
    assert MAX_CANONICAL_SYMBOLS == 30
    canonical = canonical_universe_from_groups({"FIRST": first, "SECOND": second, "THIRD": third})
    assert len(canonical) == 30


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
        configured_symbols=("XAUUSD", "EURUSD", "USDJPY"),
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
    assert calls["saved"] == ["XAUUSD", "EURUSD", "USDJPY"]
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


def validate_mobile_cards() -> None:
    from ui.field3_mobile_cards_20260722 import render_responsive_records

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeStreamlit:
        def __init__(self):
            self.markdowns: list[str] = []
            self.frames: list[tuple[pd.DataFrame, dict[str, object]]] = []

        def markdown(self, text, **kwargs):
            self.markdowns.append(text)

        def dataframe(self, frame, **kwargs):
            self.frames.append((frame.copy(), kwargs))

        def caption(self, text):
            pass

        def expander(self, *args, **kwargs):
            return FakeExpander()

    frame = pd.DataFrame([
        {
            "Rank": 1,
            "Symbol": "USDJPY",
            "Higher Regime": "BULL",
            "Middle Regime": "BULL",
            "Higher Bias": "BUY",
            "Candle After Regime Start": 3,
        }
    ])
    fake = FakeStreamlit()
    render_responsive_records(
        fake,
        {"phone_mode": True},
        frame,
        preferred_columns=["Rank", "Symbol", "Higher Regime", "Middle Regime", "Higher Bias", "Candle After Regime Start"],
        desktop_height=300,
        visualize_rank_bands=True,
        match_columns=("Higher Regime", "Middle Regime"),
    )
    assert any("f3-phone-card" in block for block in fake.markdowns)
    assert any("f3-top-five" in block and "f3-regime-match" in block for block in fake.markdowns)
    assert fake.frames and fake.frames[0][1].get("height") == 300


def validate_super_quick_top30_and_cache() -> None:
    import core.field3_three_regime_engine as field3_engine
    import core.super_quick_field3_20260722 as fast

    symbols = [f"FX{i:02d}" for i in range(30)]
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
            }
        }
    }
    context = SimpleNamespace(
        universe_id="U-TOP30",
        generation=1,
        timeframe="H1",
        loaded_symbols=tuple(symbols),
    )
    fast.get_global_symbol_context = lambda *args, **kwargs: context
    fast.publish_completed_generation = lambda *args, **kwargs: SimpleNamespace(
        publication_status="PUBLISHED", generation=1
    )
    original_persist = field3_engine.persist_field3_v2
    field3_engine.persist_field3_v2 = lambda *args, **kwargs: {"rows": 30}
    try:
        first = fast.run_super_quick_field3(state, symbols=symbols, timeframe="H1")
        second = fast.run_super_quick_field3(state, symbols=symbols, timeframe="H1")
    finally:
        field3_engine.persist_field3_v2 = original_persist
    assert first["completed_symbols"] == 30
    assert first["provider_requests"] == 0
    assert not first["reused_cached_calculation"]
    assert second["completed_symbols"] == 30
    assert second["reused_cached_calculation"]


def main() -> None:
    validate_presets()
    validate_subset_orchestration()
    validate_mobile_cards()
    validate_super_quick_top30_and_cache()
    print("ALL_SELECTOR_SEQUENTIAL_AND_FIELD3_MOBILE_TESTS_PASS")


if __name__ == "__main__":
    main()
