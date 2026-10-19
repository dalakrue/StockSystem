# Build Strategy — Streamlit Cloud deployment

The Streamlit app is now the control plane only. It queues a durable job and polls its state. It never performs the long historical download or Finder build in the Streamlit request.

## 1. Supabase

Run `supabase/build_strategy.sql` once.

Add these Streamlit Secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_..."
BUILD_STORAGE_BUCKET = "adx-build-data"
BUILD_REQUIRE_PERSISTENT = "true"
BUILD_UI_POLL_SECONDS = "3"
```

The worker uses the same Supabase URL/key as environment variables. Keep the secret key server-side only.

## 2. Worker

Deploy the `worker/` process on a separate long-running service/VM. The worker must not run inside Streamlit.

Required worker environment:

```text
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
BUILD_STORAGE_BUCKET=adx-build-data
TWELVE_DATA_API_KEY_1=...
TWELVE_DATA_API_KEY_2=...
# add _3/_4 only when available
BUILD_WORKER_POLL_SECONDS=3
BUILD_STALE_MINUTES=10
```

Start it with:

```bash
python worker/run_build_worker.py
```

For a one-job smoke test:

```bash
BUILD_WORKER_ONCE=true python worker/run_build_worker.py
```

## 3. Runtime behavior

`BUILD STRATEGY` creates a job with a default 1-year H1 target and 30-day historical chunks. Each successful chunk is stored immediately and its checkpoint is written to Supabase. A restart resumes from existing chunk objects instead of downloading them again.

After Historical Download, Finder runs symbol-by-symbol. A symbol is loaded, S1-S110 is run through the existing protected strategy audit, the Finder artifact is stored, RAM is released, and the worker advances to the next symbol.

The existing S1-S110 calculation code is not modified.

## 4. Streamlit Cloud safety

Do not start `worker/run_build_worker.py` from `app.py`, and do not create a long-lived Python thread from Streamlit. The worker is intentionally an external process.

Without Supabase configuration, Build Strategy uses a safe local fallback: the long build runs in a detached one-shot worker process and the Streamlit request remains responsive. This fallback is not durable across a Streamlit Cloud container replacement; Supabase is still required for durable cross-restart recovery. If a configured Supabase endpoint/table/storage is temporarily unavailable, the UI falls back to the same local worker path rather than crashing the page.
