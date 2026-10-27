# Check-minute data repair — 27 October 2026

This ZIP contains the full supplied application, with the check-minute repair
integrated into the shared data path used by the monthly panels. Start `app.py`.

## What is fixed

- If completed H1 history exists and only the entry-hour bar is missing, the
  app requests M15 directly through the Twelve Data key pool FIRST. It no
  longer spends the check minute retrying an unpublished H1 bar.
- The exact M15 bar opening at the required H1 hour supplies the entry open.
  Missing, invalid, later-quarter, and future opens are rejected. A historical
  completed hour requires all four quarter-hours.
- Panels share fetched data in session memory. A partial H1 fallback is NEVER
  written as completed H1 history. Actual complete provider candles can be
  retained in the existing repository.
- Provider requests run concurrently within a 20-second acquisition budget,
  with bounded request/lock timeouts and no inner sleep/retry loop. A failed
  fetch retries on a later rerender after a 15-second cooldown.
- M15-dependent systems use the same direct route with deep history. Stale
  private 10-minute wrappers no longer hide new bars.
- Root-level and numbered Streamlit Secrets/environment key names work in
  the direct path. Duplicate key values cannot multiply the local quota, and
  an old key restored from the local vault cannot shadow a new deployment secret.
- A missing key no longer enters the sidebar's API-capacity sleep loop.
  Stale symbol-name lists no longer automatically launch blocking reloads.
- Before evaluation/selection, the panel requires all 20 symbols' signal and
  entry stamps. Calculation/feature-data failures stay retryable and cannot be
  labelled a genuine no-trade. An unavailable BEST calculation cannot fall
  through to the second system as if BEST had finished silently.
- Successful no-signal checks retain 20 ranking rows, the actual entry-hour
  open, and the preceding signal candle close. Score zero on a non-firing row
  means no equation fired; it is not an invented confidence score.
- The foreground refresh timer aligns to the next check boundary and polls
  every 5 seconds during the first check minute; acquisition itself remains
  memoized and quota-limited.

The existing strategy equations, TP/SL formulas, selection priorities, and N/3
sizing rules remain in place. Data availability can change whether an existing
rule can actually run. This repair is not a new strategy validation.

## Start the app

Use Python 3.12. From this extracted folder:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

For Streamlit Community Cloud, use `app.py` as the entry file. Upload the
extracted folder contents to the app repository, preserving its folders.

## One-time key setup

In the deployed app's Streamlit Secrets, the minimum setup is:

```toml
TWELVE_DATA_API_KEY = "YOUR_REAL_KEY"
```

This is a root-level setting: put it before any `[section]` header. Locally,
use `.streamlit/secrets.toml`, which remains excluded from version control.
Do not copy unused placeholder credentials from the broader example file.
Additional configured keys are read from `[twelve_data]` `key_1` through
`key_8`, or corresponding `api_key_1` through `api_key_8` names.

The local limiter defaults to 8 requests per key per minute. Twenty missing
entry bars require up to 20 M15 requests. One key limited to 8 requests cannot
refresh all 20 inside a minute. If your actual subscription permits a higher
rate, set its REAL allowance, for example:

```toml
TWELVE_DATA_API_KEY = "YOUR_REAL_KEY"

[twelve_data]
per_key_minute_limit = 32 # EXAMPLE ONLY: use your provider's actual allowance
```

Increasing this local value does not increase the provider's allowance.
Multiple configured keys must also respect any shared account/provider limit.
Other app loading can consume credits before a check; keep sufficient capacity
available and preload history ahead of the entry window.

## Verification included

See `reports/check_minute_repair_20261027/VERIFICATION.md` and its JSON summary.
Run the repair regression checks with:

```bash
python -m pip install -r requirements-test.txt
python -m pytest tests/test_check_candle_runtime_20261027.py tests/test_canonical_20of20_completion_20261007.py tests/test_multi_api_key_pool_20261007.py -q
```

Read-only provider/evaluator evidence can be collected at a real check using:

```bash
python tools/verify_check_runtime_20261027.py --system cycle92 --report check_evidence.json
```

It reports readiness, timing, data sources, and formatted signals. It does not
place orders or certify that the deployed browser displayed them.

## Limits that remain

The supplied original ZIP already has failing legacy tests. Their failures are
documented and were compared with the repaired build; they have not all been
repaired in this check-minute update. This package is NOT certified globally
error-free.

No authenticated deployed-app check was available in this task. Actual Twelve
Data publication timing, the deployed app's secrets, and a real check-minute
browser result remain unverified. M15 can also arrive late or be unavailable;
when it does, the app must show an incomplete calculation instead of inventing
a signal. No software change can guarantee a provider publishes a bar at an
exact second. Keep the app awake and its tab active for the check.

An M15 and H1 bar must agree on symbol, provider, UTC alignment, and opening
tick for exact price equivalence. The regression tests establish arithmetic
and signal parity on controlled inputs; they do not establish equality with
another historical feed or an MT5 broker's executable price. The shown entry
is the candle open, not a guarantee that an order sent later can fill there.

Earlier dated fix reports in this ZIP describe older builds. This file and the
new verification report describe this repair.
