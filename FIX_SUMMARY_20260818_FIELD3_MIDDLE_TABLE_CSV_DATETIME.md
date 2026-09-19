# Field 3 — Middle Standard Ranking / CSV / Datetime Fix

## Fixed
- Fixed the Pandas `ValueError: cannot insert Datetime, already exists` failure by sanitizing DataFrame index metadata whenever the index name duplicates a real column name.
- Applied the protection to Field 3 ranking/evidence frames, persisted Middle-Regime history, historical Finder preparation, and current Middle snapshot creation.
- Isolated the historical Finder renderer so a malformed historical record cannot prevent the current Middle Standard Regime Ranking table from rendering.
- Made the Middle Standard CSV download independent from optional Excel generation. The CSV button is rendered as soon as the current Middle ranking exists.
- Added safe handling around the colored Excel export so an Excel-only failure cannot hide the CSV or ranking table.
- Added a regression test for a DataFrame containing both a `Datetime` column and a `Datetime`-named index.

## Validation
`python tests/test_field3_auth_finder_20260818.py`

Result: PASS.
