# Strategy Decision display and target fix

Strategy Decision now shows BUY, TP=1.00000, SL=1.00000 (or SELL), with five decimal places and no equation ID in the decision text. Equation ID and Active S Column remain separate. No trigger shows None.

Frozen symbol/month TP and SL rules supply pip distances. Valid executable broker quotes at the check supply the price basis: BUY uses ask and SELL uses bid. Without those quotes, display targets use the latest completed signal candle close; Target Price Basis explicitly marks them INDICATIVE. Actual Entry Quote stays empty and journal admission still requires a real quote. Future or forming candles never supply the reference.

Finder uses the same compact formatter and frozen equations, with its existing next-H1-open replay basis. TP/SL price aliases are synchronized. The changed engine fingerprint invalidates older strategy caches; restart and rebuild historical Finder results to refresh saved projections.

Validation: 30 tests passed in the monthly equation integration and four-year raw OHLC suites. Checked live/replay signal parity, target distances against equation evaluation, BUY/SELL and JPY formatting, timestamped quotes, missing/future quotes, Finder filtering and exports, CSV/Parquet row retention, portfolio policy, and raw-loader preservation. All Python files parsed. Frozen equation definitions and S1-S240 mapping files remain byte-identical to the uploaded source. Authenticated provider downloads and broker execution were not exercised.

Fast Strategy Build now loads and calculates one calendar year of H1 data. Full-download labels and filenames reflect the requested year count. The separate four-year raw-only loader is unchanged. One-year date bounds were checked and all seven raw-loader regression tests passed. Existing jobs retain their requested coverage; click Fast Strategy Build for a new one-year job.
