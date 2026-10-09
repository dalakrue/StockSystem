# Fixed Forex app: 240 frozen monthly equations

This is the complete app source. Extract the ZIP and run from its Forex_App_Updated folder. S1–S125 calculations are replaced by the fixed S1–S240 symbol/month mapping. Do not merge obsolete strategy calculation files into this version.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q tests/test_monthly_equations_integration.py tests/test_raw_ohlc_four_year_20261005.py
streamlit run app.py
```

On Windows activate with `.venv\Scripts\activate`. Python 3.12 was used for verification. Retain your existing provider configuration and API keys. The package includes an example secrets file; use your own existing secrets.

In Settings, load H1 candles with the existing Twelve Data controls. Run the strategy build again: old strategy caches are rejected by version, and raw candle storage remains available. The Fast Load 10-Year Raw OHLC button downloads ten calendar years of raw H1 candles for all 20 symbols without calculating strategies. The worker calculates S1–S240 from the downloaded candles. Ranking, Strategy Decision, Finder and downloads use the same map and equations. Historical equations route by each historical Myanmar check's month, and live indications route by their supplied check timestamp.

Use the **Monthly equations · S1–S240** panel for the column mapping, portfolio replay, independent diagnostics, trade logs, check decisions and all-row Parquet downloads. Historical mode may calculate all 240 equations. Strict-only mode produces zero eligible signals because every Strict_Valid flag is NO. Every historical Pip_Check remains YES; these labels do not establish fresh unseen validation or live readiness.

Run your own raw H1 dataset through the same app engine:

```bash
python scripts/replay_monthly.py --candles "/path/to/raw_ohlc.csv" --output "monthly_results"
```

Optional interval and strict mode:

```bash
python scripts/replay_monthly.py --candles "/path/to/raw_ohlc.csv" --output "strict_results" --start "2025-10-01T00:00:00Z" --end "2026-10-05T00:00:00Z" --strict-only
```

The CLI writes every raw row and all 240 signed columns to CSV/Parquet, the map, a portfolio trade log, scheduled check decisions, independent equation diagnostics and ROMAD metrics. Independent equation results use separate books and must not be summed as an executable portfolio. The frozen historical diagnostics supplied with the equations are in `reports/monthly_equations/independent_frozen_diagnostics.csv`.

## Live indication and executable-quote journal

Twelve Data H1 candles provide completed signal inputs. An H1 close or future H1 open cannot stand in for an executable live quote. Strategy Decision uses `BUY, TP=1.00000, SL=1.00000` or the corresponding SELL format. Frozen equation distances determine both targets. Without executable bid/ask evidence, numeric display targets use the latest completed signal candle close and `Target Price Basis` says `COMPLETED_CANDLE_CLOSE (INDICATIVE)`. With valid timestamped executable quotes, BUY uses ask and SELL uses bid. Finder targets use the replay entry open, labelled `REPLAY_NEXT_H1_OPEN`.

The optional broker-quote JSON input accepts this shape (replace the example prices and timestamp with real evidence):

```json
{
  "check_at": "2026-10-05T01:30:00Z",
  "quotes": {
    "EURUSD": {
      "at": "2026-10-05T01:30:00Z",
      "bid": 1.10000,
      "ask": 1.10020,
      "executable": true,
      "is_executable_open": false
    }
  }
}
```

Enter existing broker-held symbols so portfolio admission includes them. **Record current check in application journal** ranks triggers before removing held symbols, inspects four, admits at most one, enforces 20 holdings and persists deduplication in SQLite across reruns. It sends no broker orders. Unpriced/unresolved live holdings stay held. Original position equation, TP/SL, danger flag and elapsed holding limit are frozen across month changes. Broker integrations can supply quotes through `monthly_executable_quotes` and call `core.monthly_live_book`; actual order execution requires your existing broker integration and reconciliation.

Research replay fills at the next H1 open, 30 minutes after the check. It deducts 2 pips spread plus 0.5 pips slippage once. Actual bid/ask journal fills already contain the actual spread; only the 0.5 pip allowance is deducted separately, once. H1 dual touches use SL first, adverse stop gaps use the observed open, and missing execution quotes are censored with unknown P/L.

The recovered research Middle Bias formula differs from the app's heavy Middle Standard Regime display. Equations and their exits use the recovered formula; the heavy display is retained as a separate app feature.

## Verification and limits

`verification/` contains the four-year app trade log, all scheduled check decisions, portfolio metrics and verification details. The reference test retained all 531,840 raw OHLC rows and metadata, reproduced 14,932 opportunities and every one of the 9,289 previously logged independent researched entry signals. All 4,853 selected portfolio trades matched the original research simulator's entry, TP, SL, exit, net costs and censorship.

The app observes holdings at the check timestamp. The previous standalone research portfolio released holdings at the later replay fill timestamp. This timing correction changes portfolio admission and totals; it does not change the frozen equations or individual trade execution. Censored research intervals end at the next observed quote for retrospective bookkeeping with unknown P/L; this does not establish a real live position closure. The live journal never releases an unresolved holding at a fabricated price.

Max DD and ROMAD in the verification report use realized completed-trade pips. Censored outcomes have unknown P/L, so those totals are not a complete account drawdown measure. ROMAD is net pips divided by abs(Max DD), and displays n.a. for zero Max DD. The old test period was reused in equation selection. All 240 Strict_Valid flags remain NO.

Actual provider downloads and broker execution were not tested against your authenticated accounts. The loader was tested with deterministic provider responses, and executable quote handling was tested with timestamped bid/ask evidence.
