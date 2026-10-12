# External Build Strategy Worker

This process must run separately from Streamlit. It is the only process that performs long Twelve Data downloads and S1-S120 Finder builds, including the prepared two-year continuous all-symbol H1 CSV used by Fast Strategy Build. The CSV keeps every symbol/candle row and marks the chosen four through `Hourly 4 Entry`.

Required environment variables:

```text
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
BUILD_STORAGE_BUCKET=adx-build-data
TWELVE_DATA_API_KEY_1=...
TWELVE_DATA_API_KEY_2=...
BUILD_WORKER_POLL_SECONDS=3
BUILD_STALE_MINUTES=10
```

Start:

```bash
python worker/run_build_worker.py
```

One-cycle smoke test:

```bash
BUILD_WORKER_ONCE=true python worker/run_build_worker.py
```

The worker uses durable chunk objects and checkpoints. It can be restarted at any point; completed chunks and completed Finder symbols are reused.
