"""Focused non-UI validation for the 2026-06-17 final synchronization patch."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The validation environment may not install Streamlit. A tiny import stub is
# enough because these tests patch session_state and do not render widgets.
try:
    import streamlit  # type: ignore
except ModuleNotFoundError:
    import types
    streamlit = types.ModuleType("streamlit")
    streamlit.session_state = {}
    sys.modules["streamlit"] = streamlit



class FakeStreamlit:
    def __init__(self, state=None):
        self.session_state = state or {}


def validate_regime_sync() -> None:
    mod = importlib.import_module("core.regime_sync_20260617")
    now = pd.Timestamp.now().floor("h")
    ohlc = pd.DataFrame({
        "time": pd.date_range(end=now, periods=240, freq="h"),
        "open": [1.10 + i * 0.00001 for i in range(240)],
        "high": [1.1002 + i * 0.00001 for i in range(240)],
        "low": [1.0998 + i * 0.00001 for i in range(240)],
        "close": [1.10 + i * 0.00001 for i in range(240)],
    })
    # The current segment began before the 10-day display window and must not be lost.
    major = pd.DataFrame({
        "Major Regime": ["BEAR_NORMAL", "RANGE_EXPANSION"],
        "Regime Start": [now - pd.Timedelta(days=20), now - pd.Timedelta(days=12)],
        "Regime End": [now - pd.Timedelta(days=12), pd.NaT],
    })
    stale = pd.DataFrame({
        "Regime": ["BEAR_NORMAL"],
        "Time": [now - pd.Timedelta(days=30)],
    })
    nlp = pd.DataFrame({
        "Time": [now], "Rank": [1], "Title": ["EURUSD evidence"], "Impact": ["Bullish"]
    })
    state = {
        "major_regime_history_df": major,
        "dv_pp_regime_hist": stale,
        "dv_pp_df": ohlc,
        "regime_nlp_today_table": nlp,
    }
    fake = FakeStreamlit(state)
    original_st = mod.st
    original_shared = mod._shared
    mod.st = fake
    mod._shared = lambda: {
        "current": {"decision": "NO TRADE", "exit_risk": 4.0},
        "reliability_calibration": {"score": 68.0},
        "data_quality": {"score": 92.0},
        "prediction_feedback": {"samples": 0, "avg_abs_close_error_pct": 0.0, "method": "proxy"},
    }
    try:
        snap = mod.canonical_regime_snapshot(days=10)
        assert snap["regime"] == "RANGE_EXPANSION", snap
        assert pd.Timestamp(snap["regime_start"]) == now - pd.Timedelta(days=12), snap
        assert snap["regime_end_display"] == "OPEN / CURRENT", snap
        assert snap["decision"] == "BUY", snap
        assert snap["avg_error_pct"] is not None and snap["avg_error_pct"] > 0, snap
        assert snap["error_is_proxy"] is True, snap
        table = mod.merged_hourly_regime_nlp_priority(days=10)
        assert 1 <= len(table) <= 240, len(table)
        assert {"KNN Priority", "Greedy Priority", "Regime Start", "Regime End", "Regime True / False", "NLP News"}.issubset(table.columns)
        assert int((table["NLP News"] != "-").sum()) <= 1, "NLP was incorrectly copied into unrelated historical hours"
        assert table.iloc[0]["KNN Priority"] <= table.iloc[-1]["KNN Priority"]

        # Completed prediction-vs-actual rows must override a stale 0.00 summary.
        actual_hist = pd.DataFrame({
            "Actual Close": [1.1000, 1.1010, 1.1020],
            "Pred Close": [1.1005, 1.1006, 1.1028],
        })
        mod.st = FakeStreamlit({"dv_pp_bt_hist": actual_hist})
        actual_error = mod._error_snapshot({"prediction_feedback": {"avg_abs_close_error_pct": 0.0, "samples": 0}}, ohlc)
        assert actual_error["is_proxy"] is False and actual_error["samples"] == 3 and actual_error["value"] > 0, actual_error

        # With neither feedback nor OHLC, error must be N/A, not a fake 0.00 value.
        mod.st = FakeStreamlit({"major_regime_history_df": major})
        no_data = mod._error_snapshot({"prediction_feedback": {}}, pd.DataFrame())
        assert no_data["value"] is None and no_data["available"] is False, no_data

        # Mixed timezone input must not crash live API/history synchronization.
        aware_now = pd.Timestamp("2026-06-17 12:00", tz="UTC")
        aware_ohlc = pd.DataFrame({
            "time": pd.date_range(end=aware_now, periods=48, freq="h"),
            "open": 1.10, "high": 1.11, "low": 1.09,
            "close": [1.10 + i * 0.0001 for i in range(48)],
        })
        naive_regime = pd.DataFrame({
            "Regime": ["RANGE_EXPANSION"],
            "Regime Start": [pd.Timestamp("2026-06-15 00:00")],
            "Regime End": [pd.NaT],
        })
        mod.st = FakeStreamlit({"last_df": aware_ohlc, "major_regime_history_df": naive_regime})
        aware_snap = mod.canonical_regime_snapshot(days=10)
        assert aware_snap["regime"] == "RANGE_EXPANSION", aware_snap
        assert aware_snap["decision"] in {"BUY", "SELL"}, aware_snap

        # A stale, explicitly closed history row must not be relabelled current.
        closed = pd.DataFrame({
            "Regime": ["BEAR_NORMAL"],
            "Regime Start": [pd.Timestamp("2026-06-10 00:00")],
            "Regime End": [pd.Timestamp("2026-06-11 00:00")],
        })
        mod.st = FakeStreamlit({"last_df": aware_ohlc, "major_regime_history_df": closed, "current_regime": "RANGE_EXPANSION"})
        closed_snap = mod.canonical_regime_snapshot(days=10)
        assert closed_snap["regime"] == "RANGE_EXPANSION", closed_snap
        assert closed_snap["regime_end_display"] == "OPEN / CURRENT", closed_snap
    finally:
        mod.st = original_st
        mod._shared = original_shared


def validate_navigation_and_ai() -> None:
    popup = importlib.import_module("ui.liquid_menu_popup_20260615")
    assert popup.PAGES == ["Settings", "Lunch", "Dinner", "Morning", "Research", "Other"]
    assert not {"Home", "Data Visualization", "AI Assistant"}.intersection(popup.PAGES)

    other = importlib.import_module("tabs.other")
    names = [name for name, _icon, _module in other.INNER_TABS]
    for required in ["Engine", "Train Data", "Pre Original", "Backtest", "Profile"]:
        assert required in names, names

    ai = importlib.import_module("tabs.ai_assistant_lite")
    assert len(ai.PREPARED_QUESTION_PATTERNS) >= 1000, len(ai.PREPARED_QUESTION_PATTERNS)
    assert hasattr(ai, "requests"), "requests import missing; external LLM would always fall back"
    original_ai_st = ai.st
    ai.st = FakeStreamlit({
        "active_page": "Settings", "source": "TWELVE", "last_df": [1, 2, 3],
        "nlp_api_connected": True, "nlp_api_model": "test-model",
    })
    try:
        ctx = {
            "current": {
                "regime": "RANGE_EXPANSION", "decision": "BUY", "direction": "BUY",
                "exit_risk": 4.0, "entry_score": 6.1, "forecast_confidence": 62,
                "prediction_vs_actual_error": 0.04, "direction_accuracy": 55,
            },
            "data_available": True, "missing_fields": [],
        }
        parsed = ai.local_ai_detect_intent("is the sidebar restored and where is phone ui")
        assert parsed["intent"] == "system_feature_status", parsed
        answer = ai.local_ai_generate_answer(parsed, ctx)
        assert "**Safer bias:**" not in answer and "**TP / price zone:**" not in answer, answer
        quality = ai.local_ai_generate_answer(ai.local_ai_detect_intent("what is average prediction error and accuracy"), ctx)
        assert "**Safer bias:**" not in quality and "**TP / price zone:**" not in quality, quality
        trade = ai.local_ai_generate_answer(ai.local_ai_detect_intent("buy or sell safer next 1 hour"), ctx)
        assert "**Safer bias:**" in trade, trade
    finally:
        ai.st = original_ai_st


def validate_static_contracts() -> None:
    defaults = (ROOT / "core/config/defaults.py").read_text(encoding="utf-8")
    assert '"tab_choice": "Settings"' in defaults
    assert '"active_page": "Settings"' in defaults
    control = (ROOT / "ui/home_master_control_bar_20260615.py").read_text(encoding="utf-8")
    assert "position:fixed!important" in control
    assert "width:28px!important" in control and "width:32px!important" in control
    assert "[:5800]" in control
    assert "c0, c1, c2, c3" not in control
    runner = (ROOT / "core/app/runner.py").read_text(encoding="utf-8")
    assert 'initial_sidebar_state="collapsed"' in runner
    assert "install_structured_result_display" in runner
    connector = (ROOT / "ui/sidebar_fallback_panel.py").read_text(encoding="utf-8")
    assert "Finnhub Connection Status" in connector
    assert "Connect Market + NLP Together" not in connector
    assert "NLP / LLM API key" not in connector
    finnhub = (ROOT / "core/finnhub_connector.py").read_text(encoding="utf-8")
    assert 'type="password"' in finnhub
    assert "FINNHUB_BASE_URL" in finnhub
    powerbi = (ROOT / "tabs/dinner_morning_data_patch_20260614.py").read_text(encoding="utf-8")
    assert "Avg Error (Proxy)" in powerbi
    assert "recent-H1 volatility proxy" in powerbi
    lunch = (ROOT / "tabs/final_lunch_upgrade_20260617.py").read_text(encoding="utf-8")
    body = lunch.split("def render_lunch_quick_decision", 1)[1]
    assert "render_lunch_10day_backtest_expander" not in body


if __name__ == "__main__":
    validate_regime_sync()
    validate_navigation_and_ai()
    validate_static_contracts()
    print("Final synchronization validation passed.")
