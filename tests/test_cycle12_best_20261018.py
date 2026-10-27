"""Cycle 12 BEST module: verbatim equations, one check-time condition, clocks.

Reproduction test runs only when the Dukascopy H1 CSV is present
(same file the mining used); otherwise it is skipped, never failed.
"""
import numpy as np
import pandas as pd
import pytest

from core.cycle12_best import (
    BEST_EQUATIONS, CYCLE12_CHECK_HOUR_UTC, OLD_CHECK_HOURS,
    CYCLE15_VERSION, TRAIL_TRIGGER_ATR, TRAIL_DIST_ATR, dynamic_k_rule,
    add_cycle12_features, backtest_cycle12, check_time_status,
    evaluate_cycle12_signals, is_cycle12_check_time,
    is_entry_check_time, is_old_module_check_time, metrics_cycle12,
    metatrader_offset_hours, select_cycle12_entries, to_metatrader,
    to_myanmar,
)

DUKASCOPY = "/home/hatch/workspace/your_files/fx_backtest/raw_ohlc_20symbols_H1_2015-2026_dukascopy.csv"


def test_equations_verbatim_from_best_system_json():
    by_id = {e["id"]: e for e in BEST_EQUATIONS}
    assert set(by_id) == {"BEST1", "BEST2", "BEST3", "BEST4"}
    assert (by_id["BEST1"]["symbol"], by_id["BEST1"]["mom24_gt"], by_id["BEST1"]["atr_ratio_lt"],
            by_id["BEST1"]["tp_mult"], by_id["BEST1"]["sl_mult"]) == ("AUDNZD", 1.0, 1.0, 1.25, 2.5)
    assert (by_id["BEST2"]["symbol"], by_id["BEST2"]["mom24_gt"], by_id["BEST2"]["atr_ratio_lt"],
            by_id["BEST2"]["tp_mult"], by_id["BEST2"]["sl_mult"]) == ("AUDCHF", 1.0, 1.0, 1.75, 1.5)
    assert (by_id["BEST3"]["symbol"], by_id["BEST3"]["mom24_gt"], by_id["BEST3"]["atr_ratio_lt"],
            by_id["BEST3"]["tp_mult"], by_id["BEST3"]["sl_mult"]) == ("AUDCAD", 2.0, 1.0, 1.5, 1.0)
    assert (by_id["BEST4"]["symbol"], by_id["BEST4"]["mom24_gt"], by_id["BEST4"]["atr_ratio_lt"],
            by_id["BEST4"]["tp_mult"], by_id["BEST4"]["sl_mult"]) == ("NZDCAD", 1.25, 0.9, 1.5, 1.0)
    assert all(e["direction"] == "SELL" for e in BEST_EQUATIONS)


def test_old_module_07_utc_check_deleted():
    assert 7 not in OLD_CHECK_HOURS
    assert tuple(OLD_CHECK_HOURS) == (6, 10, 11, 12, 13)
    assert not is_old_module_check_time("2026-01-15 07:30")
    assert is_old_module_check_time("2026-01-15 06:30")


def test_one_check_time_condition():
    assert CYCLE12_CHECK_HOUR_UTC == 18
    assert is_cycle12_check_time("2026-01-15 18:30")  # Thursday
    assert not is_cycle12_check_time("2026-01-17 18:30")  # Saturday
    assert not is_cycle12_check_time("2026-01-15 18:00")
    assert is_entry_check_time("2026-01-15 18:30")
    assert is_entry_check_time("2026-01-15 13:30") is True  # old 13 UTC check


def test_entry_check_hours():
    # Old module: :30 of 06/10/11/12/13 UTC only; Cycle-12: 18:30 UTC.
    for h in (6, 10, 11, 12, 13, 18):
        assert is_entry_check_time(f"2026-01-15 {h:02d}:30"), h
    for h in (7, 9, 14, 15):
        assert not is_entry_check_time(f"2026-01-15 {h:02d}:30"), h


def test_clocks():
    # 18:30 UTC = 01:00 next-day Myanmar (UTC+6:30).
    assert to_myanmar("2026-01-15 18:30").strftime("%m-%d %H:%M") == "01-16 01:00"
    # MetaTrader: +3 summer, +2 winter (approx Oct 25 -> Mar 29).
    assert metatrader_offset_hours("2026-06-15 18:30") == 3
    assert metatrader_offset_hours("2026-01-15 18:30") == 2
    assert to_metatrader("2026-01-15 18:30").strftime("%H:%M") == "20:30"


def test_check_time_status_freshness():
    now = pd.Timestamp("2026-01-15 18:30", tz="UTC")
    fresh = check_time_status(now, pd.Timestamp("2026-01-15 18:00", tz="UTC"))
    assert fresh["is_entry_check_time"] is True
    assert fresh["data_updated"] is True
    stale = check_time_status(now, pd.Timestamp("2026-01-15 10:00", tz="UTC"))
    assert stale["data_updated"] is False
    unknown = check_time_status(now, None)
    assert unknown["data_updated"] is None


def test_selection_topk_and_uncapped():
    sig = pd.DataFrame([
        {"symbol": "AUDNZD", "score": 38.82}, {"symbol": "AUDCHF", "score": 22.73},
        {"symbol": "AUDCAD", "score": 22.64}, {"symbol": "NZDCAD", "score": 17.04},
    ])
    assert select_cycle12_entries(sig, k=2)["symbol"].tolist() == ["AUDNZD", "AUDCHF"]
    assert len(select_cycle12_entries(sig, k=None)) == 4
    # Max 1 open per symbol: held symbol is skipped, next-ranked taken.
    assert select_cycle12_entries(sig, open_symbols=["AUDNZD"], k=2)["symbol"].tolist() == ["AUDCHF", "AUDCAD"]


def test_features_match_b11_definitions():
    # mom24 / atr_ratio on a synthetic frame, hand-checked trend:
    # flat closes -> mom24 == 0; atr14 == range; ratio vs median.
    n = 800
    close = np.full(n, 1.1000)
    close[100:] = 1.1000 + np.arange(n - 100) * 1e-6  # tiny drift, no lookahead
    frame = pd.DataFrame({"Open": close, "High": close + 0.0010,
                          "Low": close - 0.0010, "Close": close})
    f = add_cycle12_features(frame)
    assert np.isfinite(f["atr14"].iloc[-1])
    assert abs(f["mom24"].iloc[50]) < 1e-9  # flat window -> zero momentum


@pytest.mark.skipif(not __import__("os").path.exists(DUKASCOPY),
                    reason="Dukascopy H1 CSV not present in this environment")
def test_backtest_reproduces_mining_unseen():
    import os
    raw = pd.read_csv(DUKASCOPY, usecols=["Datetime", "Symbol", "Open", "High", "Low", "Close"])
    raw["Datetime"] = pd.to_datetime(raw["Datetime"], utc=True)
    frames = {s: g.sort_values("Datetime").drop_duplicates("Datetime").set_index("Datetime")
              for s, g in raw.groupby("Symbol")}
    tr = backtest_cycle12(frames, "2025-10-05", "2026-10-05", k=2,
                        exit_mode="fixed", dynamic_k=False)
    m = metrics_cycle12(tr)
    assert m["trades"] == 163
    assert abs(m["net_pip"] - 1164.21) / 1164.21 < 0.02  # mining: +1164.21
    tr_u = backtest_cycle12(frames, "2025-10-05", "2026-10-05", k=None,
                        exit_mode="fixed", dynamic_k=False)
    m_u = metrics_cycle12(tr_u)
    assert m_u["trades"] == 186
    assert abs(m_u["net_pip"] - 1296.72) / 1296.72 < 0.02  # mining uncapped: +1296.72


def test_ft01_params_frozen():
    assert CYCLE15_VERSION == "cycle15-ft01-v1"
    assert TRAIL_TRIGGER_ATR == 1.25 and TRAIL_DIST_ATR == 0.4
    assert dynamic_k_rule(4) == 3 and dynamic_k_rule(3) == 2
    assert dynamic_k_rule(2) == 2 and dynamic_k_rule(1) == 1
    assert dynamic_k_rule(0) == 1


def test_selection_dynamic_k():
    sig = pd.DataFrame([
        {"symbol": "AUDNZD", "score": 38.82}, {"symbol": "AUDCHF", "score": 22.73},
        {"symbol": "AUDCAD", "score": 22.64}, {"symbol": "NZDCAD", "score": 17.04},
    ])
    # 4 candidates -> k=3
    assert select_cycle12_entries(sig, dynamic=True)["symbol"].tolist() == [
        "AUDNZD", "AUDCHF", "AUDCAD"]
    # 2 candidates -> k=2
    assert len(select_cycle12_entries(sig.iloc[:2], dynamic=True)) == 2
    # fixed k=2 still works (baseline)
    assert select_cycle12_entries(sig, k=2)["symbol"].tolist() == ["AUDNZD", "AUDCHF"]


@pytest.mark.skipif(not __import__("os").path.exists(DUKASCOPY),
                    reason="Dukascopy H1 CSV not present in this environment")
def test_backtest_reproduces_ft01_mining_unseen():
    import os
    raw = pd.read_csv(DUKASCOPY, usecols=["Datetime", "Symbol", "Open", "High", "Low", "Close"])
    raw["Datetime"] = pd.to_datetime(raw["Datetime"], utc=True)
    frames = {s: g.sort_values("Datetime").drop_duplicates("Datetime").set_index("Datetime")
              for s, g in raw.groupby("Symbol")}
    tr = backtest_cycle12(frames, "2025-10-05", "2026-10-05")  # FT-C01 defaults
    m = metrics_cycle12(tr)
    assert m["trades"] == 167
    assert abs(m["net_pip"] - 1283.12) / 1283.12 < 0.02  # mining FT-C01: +1283.12
