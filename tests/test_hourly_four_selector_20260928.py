import numpy as np
import pandas as pd

from core.hourly_four_symbol_selector_20260928 import add_dynamic_24h_targets, attach_hourly_four_selection
from core.strategy_audit_20260924 import build_strategy_audit


def test_dynamic_targets_are_prices_and_causal():
    n = 80
    t = pd.date_range("2026-01-01", periods=n, freq="h")
    close = 1.10 + np.linspace(0, 0.012, n)
    frame = pd.DataFrame({
        "open": close,
        "high": close + 0.0015,
        "low": close - 0.0015,
        "close": close,
        "ADX": np.linspace(18, 32, n),
        "ATR": np.full(n, 0.0025),
        "open_time": t,
    })
    out = add_dynamic_24h_targets(frame, "BUY", timeframe="H1", symbol="EURUSD")
    row = out.iloc[-1]
    assert float(row["Suggested TP"]) > float(row["close"])
    assert float(row["Suggested SL"]) < float(row["close"])
    assert float(row["Suggested TP"]) != 40.0
    assert "TP Price Display" in out.columns
    assert "SL Price Display" in out.columns

    mutated = frame.copy()
    mutated.loc[n - 1, "high"] += 1.0
    out2 = add_dynamic_24h_targets(mutated, "BUY", timeframe="H1", symbol="EURUSD")
    # Prior rows cannot change because historical range quantiles use shift(1).
    assert np.isclose(float(out.iloc[-2]["Suggested TP"]), float(out2.iloc[-2]["Suggested TP"]))
    assert np.isclose(float(out.iloc[-2]["Suggested SL"]), float(out2.iloc[-2]["Suggested SL"]))


def test_hourly_selector_keeps_exact_four_and_prefers_true_strategy_hits():
    timestamp = pd.Timestamp("2026-09-27 14:00:00", tz="UTC")
    rows = []
    for i in range(20):
        rows.append({
            "Symbol": f"SYM{i:02d}",
            "Completed Candle": timestamp,
            "Middle Regime Bias": "BUY",
            "Near Entry Score": 55 + i,
            "Best Strategy Score": 40 + i,
            "Entry Quality Passed": True,
            "TP:SL Price Ratio": 2.0,
            "24H TP Distance": 0.01 + i / 10000,
            "ATR": 0.003,
            "Suggested TP": 1.20 + i / 1000,
            "Suggested SL": 1.19 - i / 1000,
            "TP Price Display": f"{1.20 + i / 1000:.5f}",
            "SL Price Display": f"{1.19 - i / 1000:.5f}",
            "S1 Entry Condition": i == 19,
            "S1 Signal": "BUY" if i == 19 else "NO ENTRY",
            "S1 Score": 99 if i == 19 else 0,
        })
    frame = pd.DataFrame(rows)
    selected = attach_hourly_four_selection(frame)
    assert int(selected["Hourly 4 Entry"].sum()) == 4
    assert int(selected["Strategy Decision"].ne("None").sum()) == 1
    assert not selected.loc[selected.entry_origin.eq("RANK_FILL"),"entry_eligible"].any()
    assert selected.loc[selected["Symbol"].eq("SYM19"), "Hourly 4 Entry"].item() is True
    assert selected.loc[selected["Symbol"].eq("SYM19"), "Hourly Entry Origin"].item() == "STRATEGY"
    assert selected.loc[selected["Hourly 4 Entry"], "Hourly Selection Rank"].notna().all()
    assert selected.loc[selected["Hourly 4 Entry"] & selected.unique_family_count.gt(0), "Strategy Decision"].astype(str).str.match(r"BUY-\d+ TP \d+\.\d{5} SL \d+\.\d{5}$").all()
    assert selected.loc[~selected["Hourly 4 Entry"], "Strategy Decision"].eq("None").all()


def test_strategy_audit_always_emits_price_targets():
    n = 100
    t = pd.date_range("2026-01-01", periods=n, freq="h")
    rng = np.random.default_rng(7)
    base = 1.09 + np.cumsum(rng.normal(0, 0.0004, n))
    frame = pd.DataFrame({
        "open_time": t,
        "open": base,
        "high": base + 0.001,
        "low": base - 0.001,
        "close": base + rng.normal(0, 0.0001, n),
        "volume": rng.integers(100, 300, n),
    })
    audit = build_strategy_audit(frame, "BUY", "BUY", timeframe="H1")
    assert not audit.empty
    for col in ("Suggested TP", "Suggested SL", "Suggested TP Price", "Suggested SL Price", "Near Entry Score", "Strategy Hit Count"):
        assert col in audit.columns
    assert audit["Suggested TP"].notna().all()
    assert audit.loc[audit["TP Research Filters Passed"],"Suggested SL"].notna().all()
    assert not audit.loc[audit["Suggested SL"].isna(),"entry_eligible"].any()
