# Field 3 Authentication and Finder Repair — 2026-08-18

## Fixed behavior

- **Super Quick now opens Field 3.** The legacy post-run field flags incorrectly
  opened field 10 even though the visible route said Field 3. All post-run field
  flags now consistently target Field 3.
- **Long calculations no longer return an authenticated user to Login after a
  Streamlit reconnect.** A random, expiring, opaque reconnect lease restores the
  signed-in account or guest session. Only a SHA-256 hash is stored in SQLite;
  passwords and API keys are never placed in the URL.
- **Logout revokes the reconnect lease** from both account-control locations.
- **The one-use post-run destination survives a reconnect** and is removed after
  Field 3 opens.

## Middle Regime Historical Finder

- Exact start and end timestamps are inclusive and invalid/reversed ranges are
  rejected safely.
- Added presets for 7, 30, and 365 days plus all loaded history.
- Added optional Symbol and Strategy filters.
- Added a bounded paged table (25–500 rows per page) and a single-snapshot view.
- Full-range CSV remains complete even when the visible preview is filtered or
  paged; a separate filtered CSV is offered when filters are active.
- Colored Excel is now opt-in and uses one scalable `Finder Results` worksheet
  plus a `Range` worksheet. The previous worksheet-per-snapshot design could
  freeze large searches and create duplicate sheet names.
- Excel's 1,048,576-row limit is handled explicitly; CSV remains available for
  larger results.

## Verification

Run the focused regression suite:

```bash
python tests/test_field3_auth_finder_20260818.py
```

It checks session reconnect and revocation, automatic Field 3 routing, inclusive
Finder ranges, filters, paging, CSV/XLSX exports, and Super Quick historical
backfill for multiple symbols.
