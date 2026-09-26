# Middle Regime Adaptive Strategy Engine v4

The public `Strategy Decision` now comes from the five v4 families and its regime, direction and risk gates. S1–S110 remain in Finder for historical compatibility and inspection; `Legacy Strategy Decision` shows their old vote result. Legacy hits cannot create a v4 entry. The live Field 3 path and historical Finder use the same `build_strategy_audit` function. H1 rows require a fully closed UTC candle and a valid symbol session. Finder excludes incomplete rows.

`BUY Probability %`, `SELL Probability %`, TP/SL confidence and TP-before-SL fields are **heuristic model scores, not calibrated probabilities**. Prices are quote-currency levels, while `Suggested TP` and `Suggested SL` are pips (0.01 for JPY quote pairs; 0.0001 for other FX pairs). The strategy is research code and does not send orders. Forward paper testing is necessary before any performance claim or deployment to an order executor.

The symbol's prior 240 candles set its ATR expansion threshold, momentum threshold and typical range. Session windows vary for Pacific, JPY and other pairs. No current or future outcome is used to tune a historical candle. Risk gates reject a close obstacle, inadequate reward/risk, stops inside ATR noise and opposing higher pressure. `manage_trade` supplies protective stop, profit protection, bias reversal and time decay to an execution adapter. A stop is checked on every completed bar, even after 24 bars; if both TP and SL occur in one bar, SL wins. A stop earned during a bar takes effect on the next bar. The Field 3 SL display shows the initial protective price; the application has no position/order executor to call `manage_trade` automatically.

`core/adaptive_v4_research.py` groups settled outcomes by symbol, family, regime and UTC hour and reports large losses. `compare_candidate` calculates chronological unseen, walk-forward, Monte Carlo drawdown, symbol removal and nearby-parameter gates. It rejects training-only gains. The research module proposes bounded family weights from training outcomes and installs them only after its comparison gates pass. Each profile has a training cutoff, later effective date and content ID; both live and Finder invalidate cached decisions when the profile changes. No outcome-trained weights are installed in this release because the uploaded archive has no suitable ten-symbol OHLC and forward observations. Existing decisions are provisional model outputs.

## Run on Windows

1. Extract the ZIP and open a terminal in `work_a`.
2. `py -m pip install -r requirements.txt -r requirements-test.txt`
3. `py -m streamlit run app.py`
4. In Settings, load completed H1 candles, then open Field 3 and click **Build Strategies** in Finder. An older saved Finder cache is rebuilt with v4; do not treat old cache rows as v4 signals.
5. `py -m pytest -q tests/test_middle_regime_adaptive_v4.py tests/test_finder_s1_s50_repair_20260924.py tests/test_strategy_s1_s6_no_wait_20260918.py tests/test_s1_s20_finder_upgrade_20260923.py`
6. `py scripts/adaptive_v4_diagnostics.py --input your_10_symbol_H1.csv --output diagnostic.csv` to export a real ten-symbol Finder diagnostic. Input columns: `Symbol,Datetime,Open,High,Low,Close`; times are UTC candle open times. Exactly ten symbols are required. Omit `--input` for a **synthetic smoke test**.

Optional research command: `py scripts/adaptive_v4_research.py --finder diagnostic.csv --output research.json`. It groups hypothetical outcomes but does not approve strategy weights without matching cost-aware baseline, nearby parameter runs and forward evidence.

The diagnostic CSV includes `Strategy Engine=middle-regime-adaptive-v4-20260926`, `Strategy Profile=BASELINE`, regime, family, both directional scores, quote-price TP/SL, legacy S1–S110 columns and the v4 decision. This checks integration, not profitability.
